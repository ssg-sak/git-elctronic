"""Spatial join audit: chargers ↔ parking / traffic / POI.

Writes success rates + failure lists under docs/data/spatial_join/
and a markdown report docs/data/품질보고/공간조인_보고서.md.

Does NOT score or rank stations (AI·data ② scope).
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pandas as pd

SRC = Path(__file__).resolve().parent
sys.path.insert(0, str(SRC.parent))

from preprocessing import paths  # noqa: E402

REPO = paths.REPO_ROOT
SANDBOX = paths.SANDBOX_ROOT
PROC = paths.PROCESSED_DIR
OUT_DIR = REPO / "docs" / "data" / "spatial_join"
REPORT = REPO / "docs" / "data" / "공간조인_보고서.md"

RADII_M = (500, 1000, 3000)


def haversine_m(lat1, lng1, lat2, lng2) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def load_stations() -> pd.DataFrame:
    path = PROC / "charger_master.csv"
    df = pd.read_csv(path, dtype=str, low_memory=False)
    # prefer numeric coords + OK flag if present
    for c in ("lat_num", "lng_num", "lat", "lng"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    lat = df["lat_num"] if "lat_num" in df.columns else df["lat"]
    lng = df["lng_num"] if "lng_num" in df.columns else df["lng"]
    df = df.assign(lat_f=lat, lng_f=lng)
    if "coordinate_quality_flag" in df.columns:
        df = df[df["coordinate_quality_flag"] == "OK"]
    st = (
        df.dropna(subset=["lat_f", "lng_f"])
        .drop_duplicates(subset=["statId"])
        [["statId", "statNm", "addr", "lat_f", "lng_f"]]
        .reset_index(drop=True)
    )
    return st


def nearest_within(
    stations: pd.DataFrame,
    pois: pd.DataFrame,
    lat_col: str,
    lng_col: str,
    id_col: str,
    name_col: str | None,
    radius_m: float,
) -> pd.DataFrame:
    rows = []
    pois = pois.dropna(subset=[lat_col, lng_col]).copy()
    pois[lat_col] = pd.to_numeric(pois[lat_col], errors="coerce")
    pois[lng_col] = pd.to_numeric(pois[lng_col], errors="coerce")
    pois = pois.dropna(subset=[lat_col, lng_col])
    for _, s in stations.iterrows():
        best = None
        best_d = None
        for _, p in pois.iterrows():
            d = haversine_m(float(s["lat_f"]), float(s["lng_f"]), float(p[lat_col]), float(p[lng_col]))
            if d <= radius_m and (best_d is None or d < best_d):
                best_d = d
                best = p
        if best is not None:
            rows.append(
                {
                    "statId": s["statId"],
                    "statNm": s.get("statNm"),
                    "matched_id": best[id_col],
                    "matched_name": best[name_col] if name_col and name_col in best else "",
                    "distance_m": round(best_d, 1),
                    "radius_m": radius_m,
                    "matched": True,
                }
            )
        else:
            rows.append(
                {
                    "statId": s["statId"],
                    "statNm": s.get("statNm"),
                    "matched_id": "",
                    "matched_name": "",
                    "distance_m": "",
                    "radius_m": radius_m,
                    "matched": False,
                }
            )
    return pd.DataFrame(rows)


def summarize(name: str, result: pd.DataFrame, n_stations: int) -> dict:
    matched = int(result["matched"].sum())
    return {
        "layer": name,
        "radius_m": int(result["radius_m"].iloc[0]) if len(result) else None,
        "stations": n_stations,
        "matched": matched,
        "unmatched": n_stations - matched,
        "match_rate_pct": round(100.0 * matched / n_stations, 2) if n_stations else 0.0,
    }


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stations = load_stations()
    n = len(stations)

    parking = pd.read_csv(PROC / "parking_current.csv", dtype=str)
    tour = pd.read_csv(PROC / "tour_attractions_clean.csv", dtype=str)
    parks = pd.read_csv(PROC / "walk_parks_clean.csv", dtype=str)
    city_nocoord = pd.read_csv(PROC / "poi_city_tour_no_coords.csv", dtype=str)
    tour_city = pd.read_csv(PROC / "poi_tour_city_match_candidates.csv", dtype=str)

    # normalize parking/traffic coords
    if "lot" in parking.columns and "lng" not in parking.columns:
        parking = parking.rename(columns={"lot": "lng"})
    if "lat_num" in parks.columns:
        parks = parks.assign(lat=parks["lat_num"], lng=parks.get("lng", parks.get("lot")))

    layers = [
        ("parking_mock", parking, "lat", "lng" if "lng" in parking.columns else "lot", "pkltId", "pkltNm"),
        ("tour_api", tour, "lat" if "lat" in tour.columns else "mapy", "lng" if "lng" in tour.columns else "mapx", "contentid", "title"),
        ("walk_parks", parks, "lat", "lng", "mngNo", "parkNm"),
    ]

    # fix tour lat/lng from mapy/mapx if needed
    if "lat" not in tour.columns and "mapy" in tour.columns:
        tour = tour.assign(lat=pd.to_numeric(tour["mapy"], errors="coerce"), lng=pd.to_numeric(tour["mapx"], errors="coerce"))
        layers[1] = ("tour_api", tour, "lat", "lng", "contentid", "title")

    summaries = []
    fail_frames = []

    # Use 1000m as primary report radius; also compute 500/3000 for parking & tour
    primary_radius = 1000
    for name, df, la, lo, idc, nc in layers:
        # subsample stations for speed if huge — use all unique stations (~4k)
        res = nearest_within(stations, df, la, lo, idc, nc, primary_radius)
        res.to_csv(OUT_DIR / f"join_{name}_{primary_radius}m.csv", index=False, encoding="utf-8-sig")
        summaries.append(summarize(name, res, n))
        fails = res.loc[~res["matched"], ["statId", "statNm"]].copy()
        fails.insert(0, "layer", name)
        fails.insert(1, "radius_m", primary_radius)
        fails.insert(2, "reason", "NO_CANDIDATE_WITHIN_RADIUS")
        fail_frames.append(fails)

    # Multi-radius for parking only (small)
    for r in RADII_M:
        res = nearest_within(stations, parking, "lat", "lng" if "lng" in parking.columns else "lot", "pkltId", "pkltNm", r)
        summaries.append(summarize(f"parking_mock@{r}m", res, n))

    # city_tour: all fail spatial (no coords)
    city_fail = pd.DataFrame(
        {
            "layer": "city_tour",
            "radius_m": "",
            "reason": "NO_COORDINATES",
            "poi_id": city_nocoord.get("poi_id", pd.Series(dtype=str)),
            "name": city_nocoord.get("name", city_nocoord.get("attractname", pd.Series(dtype=str))),
        }
    )
    city_fail.to_csv(OUT_DIR / "fail_city_tour_no_coords.csv", index=False, encoding="utf-8-sig")

    # tour↔city name match (not spatial)
    tc = tour_city.copy()
    tc["auto_confirmed"] = tc.get("auto_confirmed", False).astype(str).str.lower().isin(["true", "1"])
    tc["needs_review"] = tc.get("needs_review", True).astype(str).str.lower().isin(["true", "1"])
    name_match_summary = {
        "layer": "tour_city_name_match",
        "candidates": len(tc),
        "auto_confirmed": int(tc["auto_confirmed"].sum()) if len(tc) else 0,
        "needs_review": int(tc["needs_review"].sum()) if len(tc) else 0,
        "tour_with_coords": len(tour),
        "city_total": len(city_nocoord),
        "city_spatial_match_rate_pct": 0.0,
        "note": "city_tour has no coordinates; name match only",
    }

    # charger quarantine failures (already known)
    qpath = SANDBOX / "data" / "quarantine" / "charger_coordinate_suspects.csv"
    q = pd.read_csv(qpath, dtype=str) if qpath.exists() else pd.DataFrame()
    q_summary = {
        "layer": "charger_coordinate_quarantine",
        "rows": len(q),
        "excluded_from_spatial_join": True,
        "flags": q["coordinate_quality_flag"].value_counts().to_dict() if len(q) and "coordinate_quality_flag" in q.columns else {},
    }

    all_fails = pd.concat(fail_frames, ignore_index=True) if fail_frames else pd.DataFrame()
    # keep manageable fail list: unmatched only sample? keep all unmatched ids per layer — can be large
    # For 4k stations * 5 layers mostly unmatched with only 12 parkings — fail list huge.
    # Store rates + top: write unmatched counts only and sample 50 fails per layer
    samples = []
    for name, _, _, _, _, _ in layers:
        part = all_fails[all_fails["layer"] == name].head(50)
        samples.append(part)
    sample_fails = pd.concat(samples, ignore_index=True) if samples else pd.DataFrame()
    sample_fails.to_csv(OUT_DIR / "fail_sample_unmatched_50_per_layer.csv", index=False, encoding="utf-8-sig")

    meta = {
        "stations_ok_coords": n,
        "primary_radius_m": primary_radius,
        "layer_summaries": summaries,
        "name_match": name_match_summary,
        "quarantine": q_summary,
        "outputs": {
            "dir": str(OUT_DIR.relative_to(REPO)).replace("\\", "/"),
            "fail_city_tour": "fail_city_tour_no_coords.csv",
            "fail_sample": "fail_sample_unmatched_50_per_layer.csv",
        },
    }
    (OUT_DIR / "spatial_join_summary.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # markdown report
    lines = [
        "# 공간 결합 매칭 보고",
        "",
        "| 항목 | 내용 |",
        "|---|---|",
        "| **역할** | AI·데이터 ① — 공간 결합 |",
        "| **작성** | 2026-07-20 |",
        "| **완료 기준** | 매칭 성공률과 실패 목록 기록 |",
        "| **기준 충전소** | `coordinate_quality_flag=OK` 고유 `statId` |",
        f"| **충전소 수** | {n:,} |",
        f"| **주 반경** | {primary_radius} m (하버사인) |",
        "| **산출** | `docs/data/spatial_join/` |",
        "",
        "> 점수·패널티 반영은 ② 영역. 본 보고는 **결합 가능 여부·커버리지**만 다룬다.",
        "",
        "---",
        "",
        "## 1. 레이어별 매칭 성공률 (최근접 1건 ≤ 반경)",
        "",
        "| 레이어 | 반경(m) | 매칭 | 미매칭 | 성공률(%) | 비고 |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for s in summaries:
        note = "mock" if "mock" in s["layer"] else ""
        lines.append(
            f"| {s['layer']} | {s['radius_m']} | {s['matched']:,} | {s['unmatched']:,} | {s['match_rate_pct']} | {note} |"
        )

    lines += [
        "",
        "## 2. 실패·제외 목록",
        "",
        "### 2.1 좌표 격리 충전기 (공간결합 제외)",
        "",
        f"- 건수: **{q_summary['rows']}**",
        f"- 플래그: `{q_summary['flags']}`",
        f"- 파일: `SANDBOX_.../data/quarantine/charger_coordinate_suspects.csv`",
        "",
        "### 2.2 대구시 관광지 (무좌표 → 공간결합 실패 100%)",
        "",
        f"- 건수: **{len(city_nocoord)}**",
        f"- 사유: `NO_COORDINATES`",
        f"- 목록: `docs/data/spatial_join/fail_city_tour_no_coords.csv`",
        "",
        "### 2.3 TourAPI ↔ city_tour 이름 후보 (비공간)",
        "",
        f"- 후보: {name_match_summary['candidates']} · 자동확정 {name_match_summary['auto_confirmed']} · 검토필요 {name_match_summary['needs_review']}",
        f"- Tour 좌표 O: {name_match_summary['tour_with_coords']} / city 전체: {name_match_summary['city_total']}",
        "- 파일: SANDBOX `poi_tour_city_match_candidates.csv`",
        "",
        "### 2.4 반경 내 후보 없음 (샘플)",
        "",
        "- mock 주차·교통은 건수가 적어 **대부분 충전소가 미매칭**인 것이 정상이다.",
        "- 레이어별 미매칭 50건 샘플: `docs/data/spatial_join/fail_sample_unmatched_50_per_layer.csv`",
        "- 전체 조인 결과(성공+실패): `join_<layer>_1000m.csv`",
        "",
        "## 3. 해석 (①)",
        "",
        "| 관찰 | 의미 |",
        "|---|---|",
        "| 주차·교통 mock 성공률 낮음 | 실데이터가 아니라 **스키마·거리 조인 검증** 단계 |",
        "| city_tour 239 전부 실패 | 지오코딩 전까지 공간 피처 불가 |",
        "| Tour·공원은 좌표 있음 | 반경 POI 밀도 피처 후보로 사용 가능 |",
        "| 좌표 quarantine 27 | 거리 조인·지도에서 제외 |",
        "",
        "## 4. 재실행",
        "",
        "```bash",
        "python apps/data-pipeline/evaluation/personal/experiments/SANDBOX_20260716_preprocess_pipeline/src/preprocessing/spatial_join_audit.py",
        "```",
        "",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"stations": n, "summaries": summaries, "report": str(REPORT)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
