"""DA① offline ETA calibration: multi-origin TMAP sample vs haversine.

Does NOT fill D1 eta_minutes and is NOT a collection loop.
Builds a small calibration table so ② can map distance→ETA proxy until BE
fills runtime TMAP on the final 3~5 candidates.

Usage:
  python apps/data-pipeline/processing/analysis/build_eta_calibration.py
  python apps/data-pipeline/processing/analysis/build_eta_calibration.py --per-origin 20
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import requests
from dotenv import load_dotenv

_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))
from _bootstrap import ensure_paths

REPO = ensure_paths()
from features.use_time import is_operating_now  # noqa: E402

KST = ZoneInfo("Asia/Seoul")
TMAP_URL = "https://apis.openapi.sk.com/tmap/routes"
ASSUME_SPEED_KMH = 30.0

ORIGINS = [
    {"id": "dongdaegu", "label": "동대구역 인근", "lat": 35.8797, "lng": 128.6284},
    {"id": "banwoldang", "label": "반월당 인근", "lat": 35.8655, "lng": 128.5936},
    {"id": "suseong", "label": "수성못 인근", "lat": 35.8280, "lng": 128.6180},
    {"id": "seongseo", "label": "성서 인근", "lat": 35.8515, "lng": 128.5085},
]

plt.rcParams["font.family"] = ["Malgun Gothic", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(a))


def _tmap_route(
    app_key: str, start_lat: float, start_lng: float, end_lat: float, end_lng: float
) -> dict:
    headers = {
        "appKey": app_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    body = {
        "startX": str(start_lng),
        "startY": str(start_lat),
        "endX": str(end_lng),
        "endY": str(end_lat),
        "reqCoordType": "WGS84GEO",
        "resCoordType": "WGS84GEO",
        "searchOption": "0",
        "trafficInfo": "Y",
    }
    r = requests.post(
        TMAP_URL,
        params={"version": "1", "format": "json"},
        headers=headers,
        json=body,
        timeout=30,
    )
    out: dict = {
        "http_status": r.status_code,
        "eta_seconds": None,
        "road_distance_m": None,
        "error": None,
    }
    if r.status_code != 200:
        out["error"] = (r.text or "")[:300]
        return out
    try:
        data = r.json()
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"json: {exc}"
        return out
    for f in data.get("features") or []:
        props = (f or {}).get("properties") or {}
        if "totalTime" in props:
            out["eta_seconds"] = int(props["totalTime"])
            if props.get("totalDistance") is not None:
                out["road_distance_m"] = int(props["totalDistance"])
            return out
    out["error"] = "no totalTime in features"
    return out


def _load_public_stations() -> tuple[pd.DataFrame, str]:
    d1_path = (
        REPO
        / "apps/data-pipeline/evaluation/results/datasets/station_feature_snapshot_latest.csv"
    )
    d1 = pd.read_csv(d1_path, dtype=str, low_memory=False)
    for c in ("lat", "lng"):
        d1[c] = pd.to_numeric(d1[c], errors="coerce")
    pub = d1["recommend_public_default"].astype(str).str.lower().isin(["true", "1"])
    ok = d1["coord_ok"].astype(str).str.lower().isin(["true", "1"])
    stations = (
        d1.loc[pub & ok]
        .dropna(subset=["lat", "lng"])
        .drop_duplicates(subset=["statId"], keep="first")
        .copy()
    )
    if "useTime" not in stations.columns:
        stations["useTime"] = pd.NA
    return stations, str(d1_path.relative_to(REPO)).replace("\\", "/")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-origin", type=int, default=16)
    parser.add_argument("--sleep", type=float, default=0.35)
    parser.add_argument(
        "--max-km",
        type=float,
        default=8.0,
        help="only sample stations within this haversine km of each origin",
    )
    parser.add_argument(
        "--stratified",
        action="store_true",
        default=True,
        help="sample across 0-2/2-4/4-6/6-8km bands (default on)",
    )
    parser.add_argument("--no-stratified", action="store_false", dest="stratified")
    args = parser.parse_args()

    load_dotenv(REPO / ".env")
    app_key = (os.getenv("TMAP_APP_KEY") or "").strip()
    if not app_key or "MOCK" in app_key.upper():
        print("FAIL: TMAP_APP_KEY missing or mock")
        return 1

    stations, source_label = _load_public_stations()
    if stations.empty:
        print("FAIL: no public candidates")
        return 1

    now = datetime.now(KST)
    stamp = now.strftime("%Y%m%d")
    rows: list[dict] = []
    call_i = 0
    planned = len(ORIGINS) * args.per_origin

    for origin in ORIGINS:
        s = stations.copy()
        s["haversine_km"] = s.apply(
            lambda r: _haversine_km(
                origin["lat"], origin["lng"], float(r["lat"]), float(r["lng"])
            ),
            axis=1,
        )
        s = s.loc[s["haversine_km"] <= args.max_km]
        if args.stratified:
            band_edges = [0.0, 2.0, 4.0, 6.0, 8.0]
            per_band = max(1, args.per_origin // (len(band_edges) - 1))
            parts: list[pd.DataFrame] = []
            for lo, hi in zip(band_edges[:-1], band_edges[1:]):
                band = s.loc[(s["haversine_km"] >= lo) & (s["haversine_km"] < hi)]
                if band.empty:
                    continue
                # spread within band: take evenly spaced by rank
                band = band.sort_values("haversine_km")
                n_take = min(per_band, len(band))
                idx = [
                    int(round(i * (len(band) - 1) / max(n_take - 1, 1)))
                    for i in range(n_take)
                ]
                parts.append(band.iloc[sorted(set(idx))])
            sample = (
                pd.concat(parts, ignore_index=True)
                .drop_duplicates(subset=["statId"])
                .head(args.per_origin)
                .reset_index(drop=True)
            )
        else:
            sample = s.nsmallest(args.per_origin, "haversine_km").reset_index(drop=True)
        for i, r in sample.iterrows():
            call_i += 1
            tmap = _tmap_route(
                app_key,
                origin["lat"],
                origin["lng"],
                float(r["lat"]),
                float(r["lng"]),
            )
            eta_sec = tmap["eta_seconds"]
            eta_min = round(eta_sec / 60, 1) if eta_sec is not None else None
            hv_min = round(float(r["haversine_km"]) / ASSUME_SPEED_KMH * 60, 1)
            arrive = now + timedelta(seconds=eta_sec) if eta_sec is not None else None
            open_at = (
                is_operating_now(r.get("useTime"), arrive)
                if arrive is not None
                else "UNKNOWN"
            )
            keep = (
                "DROP"
                if open_at == "N"
                else ("KEEP" if open_at == "Y" else "REVIEW")
            )
            ratio = (
                round(eta_min / hv_min, 3)
                if eta_min and hv_min and hv_min > 0
                else None
            )
            row = {
                "origin_id": origin["id"],
                "origin_label": origin["label"],
                "origin_lat": origin["lat"],
                "origin_lng": origin["lng"],
                "rank_by_haversine": int(i) + 1,
                "statId": r["statId"],
                "statNm": r["statNm"],
                "lat": float(r["lat"]),
                "lng": float(r["lng"]),
                "haversine_km": round(float(r["haversine_km"]), 3),
                "haversine_eta_min_proxy": hv_min,
                "tmap_eta_min": eta_min,
                "tmap_road_km": round(tmap["road_distance_m"] / 1000, 3)
                if tmap["road_distance_m"] is not None
                else None,
                "eta_ratio_tmap_over_haversine": ratio,
                "da_arrival_gate": keep,
                "is_operating_at_arrival": open_at,
                "tmap_http": tmap["http_status"],
                "tmap_error": tmap["error"],
                "as_of_kst": now.isoformat(timespec="seconds"),
            }
            rows.append(row)
            print(
                f"[{call_i}/{planned}] {origin['id']} {r['statId']} "
                f"hv={row['haversine_km']}km tmap={eta_min} ratio={ratio}"
            )
            time.sleep(args.sleep)

    df = pd.DataFrame(rows)
    out = REPO / f"docs/data/analysis/eta_calibration_{stamp}"
    share = REPO / "docs" / "팀공유" / f"ETA_보정샘플_{stamp}"
    fig_dir = out / "figures"
    for p in (fig_dir, share / "figures", share / "data"):
        p.mkdir(parents=True, exist_ok=True)

    csv_path = out / "eta_calibration_samples.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    df.to_csv(share / "data" / "eta_calibration_samples.csv", index=False, encoding="utf-8-sig")

    ok = df["tmap_eta_min"].notna()
    ok_df = df.loc[ok].copy()
    bands = [(0, 2), (2, 4), (4, 6), (6, 8)]
    band_rows = []
    for lo, hi in bands:
        sub = ok_df.loc[
            (ok_df["haversine_km"] >= lo) & (ok_df["haversine_km"] < hi),
            "eta_ratio_tmap_over_haversine",
        ].dropna()
        band_rows.append(
            {
                "haversine_km_lo": lo,
                "haversine_km_hi": hi,
                "n": int(len(sub)),
                "ratio_median": float(sub.median()) if len(sub) else None,
                "ratio_p25": float(sub.quantile(0.25)) if len(sub) else None,
                "ratio_p75": float(sub.quantile(0.75)) if len(sub) else None,
                "tmap_eta_min_median": float(
                    ok_df.loc[
                        (ok_df["haversine_km"] >= lo) & (ok_df["haversine_km"] < hi),
                        "tmap_eta_min",
                    ].median()
                )
                if len(sub)
                else None,
            }
        )
    band_df = pd.DataFrame(band_rows)
    band_df.to_csv(out / "eta_ratio_by_distance_band.csv", index=False, encoding="utf-8-sig")
    band_df.to_csv(
        share / "data" / "eta_ratio_by_distance_band.csv",
        index=False,
        encoding="utf-8-sig",
    )

    global_ratio = (
        float(ok_df["eta_ratio_tmap_over_haversine"].median()) if len(ok_df) else None
    )
    calibration = {
        "role": "DA① offline calibration — not runtime ETA authority",
        "as_of_kst": now.isoformat(timespec="seconds"),
        "origin_count": len(ORIGINS),
        "per_origin": args.per_origin,
        "max_km": args.max_km,
        "haversine_speed_proxy_kmh": ASSUME_SPEED_KMH,
        "candidate_source": source_label,
        "tmap_ok": int(ok.sum()),
        "tmap_fail": int((~ok).sum()),
        "ratio_tmap_over_haversine_median": global_ratio,
        "ratio_by_band": band_rows,
        "proxy_formula": (
            "eta_proxy_min = haversine_km / 30 * 60 * ratio_median_band "
            "(fallback global median). Runtime truth = BE TMAP on final 3~5."
        ),
        "do_not": [
            "bulk-fill D1 eta_minutes",
            "replace BE TMAP at serve time",
            "use link_speed alone as ETA",
        ],
    }
    (out / "calibration.json").write_text(
        json.dumps(calibration, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (share / "data" / "calibration.json").write_text(
        json.dumps(calibration, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # figures
    if len(ok_df):
        fig, ax = plt.subplots(figsize=(7.5, 5.5), facecolor="#f7f8fa")
        for oid, g in ok_df.groupby("origin_id"):
            ax.scatter(
                g["haversine_km"],
                g["tmap_eta_min"],
                s=28,
                alpha=0.75,
                label=oid,
            )
        xmax = float(ok_df["haversine_km"].max())
        xs = pd.Series([0, xmax])
        ax.plot(
            xs,
            xs / ASSUME_SPEED_KMH * 60,
            color="#8899aa",
            ls="--",
            label="haversine@30km/h",
        )
        if global_ratio:
            ax.plot(
                xs,
                xs / ASSUME_SPEED_KMH * 60 * global_ratio,
                color="#c45c26",
                ls="-",
                label=f"calibrated×{global_ratio:.2f}",
            )
        ax.set_xlabel("haversine_km")
        ax.set_ylabel("tmap_eta_min")
        ax.set_title("TMAP ETA vs haversine (multi-origin)", loc="left", fontweight="bold")
        ax.legend(frameon=False, fontsize=8)
        ax.spines[["top", "right"]].set_visible(False)
        fig.tight_layout()
        for dest in (fig_dir, share / "figures"):
            fig.savefig(dest / "01_tmap_vs_haversine.png", dpi=160, bbox_inches="tight")
        plt.close(fig)

        fig, ax = plt.subplots(figsize=(7, 4.2), facecolor="#f7f8fa")
        plot_b = band_df.dropna(subset=["ratio_median"])
        ax.bar(
            [f"{int(r.haversine_km_lo)}-{int(r.haversine_km_hi)}km" for r in plot_b.itertuples()],
            plot_b["ratio_median"],
            color="#2f6f4e",
        )
        ax.axhline(1.0, color="#8899aa", ls=":", lw=1)
        if global_ratio:
            ax.axhline(global_ratio, color="#c45c26", ls="--", lw=1, label=f"global {global_ratio:.2f}")
        ax.set_ylabel("median(tmap / haversine_proxy)")
        ax.set_title("ETA ratio by distance band", loc="left", fontweight="bold")
        ax.legend(frameon=False)
        ax.spines[["top", "right"]].set_visible(False)
        fig.tight_layout()
        for dest in (fig_dir, share / "figures"):
            fig.savefig(dest / "02_ratio_by_band.png", dpi=160, bbox_inches="tight")
        plt.close(fig)

    readme = f"""# ETA 보정 샘플 — {stamp}

| 항목 | 값 |
|---|---|
| 역할 | DA① **오프라인 보정** (런타임 ETA 권한 아님) |
| 출발지 | {len(ORIGINS)}곳 × 각 {args.per_origin}소 (≤{args.max_km}km) |
| TMAP 성공 | **{int(ok.sum())}/{len(df)}** |
| 전역 보정비 (tmap/hv@30) median | **{global_ratio}** |
| 후보 | 공용·coord_ok (`{source_label}`) |

## ②·BE 쓰는 법

1. **서빙 정본:** 최종 후보 3~5곳만 BE가 TMAP 호출 → `eta_minutes`
2. **학습/리플레이 보조:** `eta_proxy_min ≈ haversine_km/30*60 * ratio_band`  
   (`data/calibration.json` · `eta_ratio_by_distance_band.csv`)
3. D1 `eta_minutes` **일괄 채우지 않음**
4. 도착×useTime 게이트 샘플 컬럼 `da_arrival_gate` 참고

## 그림

- `figures/01_tmap_vs_haversine.png`
- `figures/02_ratio_by_band.png`

```
DA① | ETA calibration sample | {stamp}
```
"""
    (out / "README.md").write_text(readme, encoding="utf-8")
    (share / "README.md").write_text(readme, encoding="utf-8")

    handoff = REPO / "docs" / "팀공유" / f"팀공유_ETA_보정_20260806.md"
    handoff.write_text(
        "\n".join(
            [
                "# 팀 공유 — DA① ETA 보정 샘플 (2026-08-06)",
                "",
                "## 한 일",
                f"- 출발지 {len(ORIGINS)} · 공용 후보 각 {args.per_origin}곳 TMAP `/routes`",
                f"- 성공 **{int(ok.sum())}/{len(df)}** · 전역 ratio median **{global_ratio}**",
                f"- 산출: `{out.relative_to(REPO).as_posix()}/` · 팀공유 `{share.name}/`",
                "",
                "## 계약",
                "- 런타임 ETA 권한 = **백엔드 TMAP** (최종 3~5)",
                "- ① 보정은 **오프라인 보정·horizon 대체 설명**용",
                "- D1 `eta_minutes` null 예약 유지",
                "",
                "```",
                "DA① | ETA calibration | 20260806",
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(json.dumps(calibration, ensure_ascii=True, indent=2))
    print("SHARE", share)
    return 0 if int(ok.sum()) > 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
