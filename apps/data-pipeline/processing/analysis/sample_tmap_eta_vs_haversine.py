"""DA① one-shot: haversine vs TMAP ETA sample + arrival×useTime filter.

Not a collection loop. Calls TMAP only for ~15 final candidates from a fixed
Daegu origin. Requires TMAP_APP_KEY in repo .env.

Outputs under docs/data/analysis/tmap_eta_sample_<YYYYMMDD>/.
"""
from __future__ import annotations

import json
import math
import os
import time
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

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

# Dongdaegu Station vicinity — representative origin for MVP demos
ORIGIN_LAT = 35.8797
ORIGIN_LNG = 128.6284
ORIGIN_LABEL = "동대구역 인근"
SAMPLE_N = 15
ASSUME_SPEED_KMH = 30.0  # haversine → rough minute proxy (not road ETA)


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
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
    feats = data.get("features") or []
    for f in feats:
        props = (f or {}).get("properties") or {}
        if "totalTime" in props:
            out["eta_seconds"] = int(props["totalTime"])
            out["road_distance_m"] = (
                int(props["totalDistance"]) if props.get("totalDistance") is not None else None
            )
            return out
    out["error"] = "no totalTime in features"
    return out


def main() -> int:
    load_dotenv(REPO / ".env")
    app_key = (os.getenv("TMAP_APP_KEY") or "").strip()
    if not app_key or "MOCK" in app_key.upper():
        print("FAIL: TMAP_APP_KEY missing or mock — DA sample needs a real key")
        return 1

    # Prefer current D1 public candidates; fall back to static info extract.
    d1_path = (
        REPO
        / "apps/data-pipeline/evaluation/results/datasets/station_feature_snapshot_latest.csv"
    )
    hours_path = REPO / "docs/data/extracted/charger/hours/daegu_charger_hours_latest.csv"
    info_path = REPO / "docs/data/extracted/charger/info/daegu_charger_info_20260723_latest.csv"
    source_label = ""

    if d1_path.is_file():
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
        source_label = str(d1_path.relative_to(REPO)).replace("\\", "/")
        info_path = d1_path
    else:
        if not info_path.is_file():
            print(f"FAIL: missing {info_path}")
            return 1
        info = pd.read_csv(info_path, dtype=str)
        for c in ("lat", "lng"):
            info[c] = pd.to_numeric(info[c], errors="coerce")
        stations = (
            info.dropna(subset=["lat", "lng"])
            .drop_duplicates(subset=["statId"], keep="first")
            .copy()
        )
        source_label = str(info_path.relative_to(REPO)).replace("\\", "/")

    if stations.empty:
        print("FAIL: no candidate stations")
        return 1

    stations["haversine_km"] = stations.apply(
        lambda r: _haversine_km(ORIGIN_LAT, ORIGIN_LNG, float(r["lat"]), float(r["lng"])),
        axis=1,
    )
    stations["haversine_eta_min"] = (stations["haversine_km"] / ASSUME_SPEED_KMH * 60).round(1)
    sample = stations.nsmallest(SAMPLE_N, "haversine_km").reset_index(drop=True)

    now = datetime.now(KST)
    rows: list[dict] = []
    for i, r in sample.iterrows():
        tmap = _tmap_route(
            app_key, ORIGIN_LAT, ORIGIN_LNG, float(r["lat"]), float(r["lng"])
        )
        eta_sec = tmap["eta_seconds"]
        eta_min = round(eta_sec / 60, 1) if eta_sec is not None else None
        arrive = now + timedelta(seconds=eta_sec) if eta_sec is not None else None
        use_time = r.get("useTime")
        open_now = is_operating_now(use_time, now)
        open_at_arrive = is_operating_now(use_time, arrive) if arrive else "UNKNOWN"
        # DA gate: drop if closed at arrival (UNKNOWN kept for BE policy)
        keep = "DROP" if open_at_arrive == "N" else ("KEEP" if open_at_arrive == "Y" else "REVIEW")
        row = {
            "rank_by_haversine": i + 1,
            "statId": r["statId"],
            "statNm": r["statNm"],
            "lat": r["lat"],
            "lng": r["lng"],
            "useTime": use_time,
            "haversine_km": round(float(r["haversine_km"]), 3),
            "haversine_eta_min_proxy": float(r["haversine_eta_min"]),
            "tmap_eta_min": eta_min,
            "tmap_road_km": round(tmap["road_distance_m"] / 1000, 3)
            if tmap["road_distance_m"] is not None
            else None,
            "eta_ratio_tmap_over_haversine": round(eta_min / float(r["haversine_eta_min"]), 2)
            if eta_min and float(r["haversine_eta_min"]) > 0
            else None,
            "as_of_kst": now.isoformat(timespec="seconds"),
            "arrive_kst": arrive.isoformat(timespec="seconds") if arrive else None,
            "is_operating_now": open_now,
            "is_operating_at_arrival": open_at_arrive,
            "da_arrival_gate": keep,
            "tmap_http": tmap["http_status"],
            "tmap_error": tmap["error"],
        }
        rows.append(row)
        print(
            f"[{i+1}/{SAMPLE_N}] {r['statId']} hv={row['haversine_km']}km "
            f"tmap={eta_min}min gate={keep} err={tmap['error']}"
        )
        time.sleep(0.35)

    out_dir = REPO / f"docs/data/analysis/tmap_eta_sample_{now.strftime('%Y%m%d')}"
    out_dir.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    csv_path = out_dir / "haversine_vs_tmap_eta.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")

    ok = df["tmap_eta_min"].notna().sum()
    meta = {
        "role": "DA① sample only — not a collection loop",
        "origin": {"label": ORIGIN_LABEL, "lat": ORIGIN_LAT, "lng": ORIGIN_LNG},
        "sample_n": SAMPLE_N,
        "tmap_ok": int(ok),
        "tmap_fail": int(SAMPLE_N - ok),
        "as_of_kst": now.isoformat(timespec="seconds"),
        "haversine_speed_proxy_kmh": ASSUME_SPEED_KMH,
        "info_source": source_label,
        "hours_source": str(hours_path.relative_to(REPO)) if hours_path.is_file() else None,
        "candidate_filter": "recommend_public_default & coord_ok from D1 when available",
        "outputs": {
            "csv": str(csv_path.relative_to(REPO)),
        },
    }
    (out_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Short markdown for team
    md_lines = [
        "# DA① TMAP ETA 샘플 (직선거리 대비)",
        "",
        "## 범위",
        "- **하는 일**: 동대구역 인근 기준 가까운 **공용** 충전소 **15곳**만 TMAP `/tmap/routes` 1회씩 호출 → 직선거리·ETA 비교 + **도착시각×useTime** 게이트",
        "- **안 하는 일**: TMAP 수집 루프, D1 `eta_minutes` 일괄 채우기, 백엔드 `/routes` API, 프론트 키 노출",
        "",
        f"- 기준점: {ORIGIN_LABEL} ({ORIGIN_LAT}, {ORIGIN_LNG})",
        f"- 후보 소스: `{source_label}`",
        f"- 시각(KST): {now.isoformat(timespec='seconds')}",
        f"- TMAP 성공: **{ok}/{SAMPLE_N}**",
        "",
        "## 산출",
        f"- `{csv_path.relative_to(REPO).as_posix()}`",
        f"- `{ (out_dir / 'meta.json').relative_to(REPO).as_posix() }`",
        "",
        "## 백엔드에 넘길 계약",
        "1. 추천 응답의 `eta_minutes`는 **백엔드가 TMAP으로 채움** (DA 테이블은 null 예약)",
        "2. 후보 정렬 전: `is_operating_at_arrival` — `N`이면 탈락/최하위, `UNKNOWN`은 열린 것으로 치지 말 것",
        "3. DA 파서: `apps/data-pipeline/processing/features/use_time.py`",
        "",
        "| rank | statId | haversine_km | tmap_eta_min | gate |",
        "|------|--------|--------------|--------------|------|",
    ]
    for _, row in df.iterrows():
        md_lines.append(
            f"| {row['rank_by_haversine']} | {row['statId']} | {row['haversine_km']} | "
            f"{row['tmap_eta_min']} | {row['da_arrival_gate']} |"
        )
    md_path = out_dir / "README.md"
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    handoff = REPO / "docs/팀공유/팀공유_TMAP_ETA_샘플_20260723.md"
    handoff.write_text(
        "\n".join(
            [
                "# 팀 공유 — DA① TMAP ETA 샘플 + 도착×useTime (2026-07-23)",
                "",
                "## DA①가 한 것",
                f"- 동대구역 인근 → 가까운 충전소 {SAMPLE_N}곳 TMAP ETA 1회 샘플",
                f"- TMAP 성공 **{ok}/{SAMPLE_N}**",
                f"- 산출: `docs/data/analysis/tmap_eta_sample_{now.strftime('%Y%m%d')}/`",
                "",
                "## 백엔드가 할 것",
                "- 요청 시점에 최종 후보 3~5곳만 TMAP 호출 → `eta_minutes` 채움",
                "- 정렬 전 도착시각 기준 useTime 필터 (DA `is_operating_now`)",
                "",
                "## DA①가 안 하는 것",
                "- TMAP 수집 루프 / Lightsail 주기 호출",
                "- `apps/api` 라우트 구현",
                "",
                "```",
                "DA① | TMAP sample + arrival useTime gate | 2026-07-23",
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(f"OK wrote {csv_path}")
    print(f"OK wrote {handoff}")
    return 0 if ok > 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
