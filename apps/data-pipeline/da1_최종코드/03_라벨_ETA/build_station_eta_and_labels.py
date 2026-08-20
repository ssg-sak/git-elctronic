"""Fetch real TMAP ETA for all public D1 candidates + arrival labels from panel.

- ETA: TMAP /tmap/routes from a fixed origin (default 동대구역) for every
  recommend_public_default & coord_ok station. Checkpoint/resume supported.
- Labels: for each panel row of those stations, look ahead by that station's
  TMAP eta_minutes → target_available_at_arrival.

Does NOT replace BE runtime ETA authority for live API responses, but DOES
materialize real ETA numbers + training labels for ②.

Usage:
  python apps/data-pipeline/processing/analysis/build_station_eta_and_labels.py
  python apps/data-pipeline/processing/analysis/build_station_eta_and_labels.py --eta-only
  python apps/data-pipeline/processing/analysis/build_station_eta_and_labels.py --labels-only
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv

_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))
from _bootstrap import ensure_paths

REPO = ensure_paths()

KST = ZoneInfo("Asia/Seoul")
TMAP_URL = "https://apis.openapi.sk.com/tmap/routes"
ORIGIN = {
    "id": "dongdaegu",
    "label": "동대구역 인근",
    "lat": 35.8797,
    "lng": 128.6284,
}
ASSUME_SPEED_KMH = 30.0
TARGET_TOLERANCE_MINUTES = 7.5
SEGMENT_GAP_MINUTES = 25

OUT_DIR = REPO / "apps/data-pipeline/evaluation/results/datasets"
ANALYSIS_DIR = REPO / "docs/data/analysis"
SHARE = REPO / "docs" / "팀공유"


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
    out["error"] = "no totalTime"
    return out


def _load_candidates() -> pd.DataFrame:
    d1_path = OUT_DIR / "station_feature_snapshot_latest.csv"
    d1 = pd.read_csv(d1_path, encoding="utf-8-sig", low_memory=False)
    for c in ("lat", "lng"):
        d1[c] = pd.to_numeric(d1[c], errors="coerce")
    pub = d1["recommend_public_default"].astype(str).str.lower().isin(["true", "1"])
    ok = d1["coord_ok"].astype(str).str.lower().isin(["true", "1"])
    cols = [
        c
        for c in (
            "statId",
            "statNm",
            "lat",
            "lng",
            "useTime",
            "total_chargers",
            "available_count",
            "observation_state",
            "as_of_ts",
        )
        if c in d1.columns
    ]
    return (
        d1.loc[pub & ok, cols]
        .dropna(subset=["lat", "lng"])
        .drop_duplicates(subset=["statId"])
        .reset_index(drop=True)
    )


def fetch_eta(*, sleep_s: float, limit: int | None) -> Path:
    load_dotenv(REPO / ".env")
    app_key = (os.getenv("TMAP_APP_KEY") or "").strip()
    if not app_key or "MOCK" in app_key.upper():
        raise RuntimeError("TMAP_APP_KEY missing or mock")

    cands = _load_candidates()
    if limit:
        cands = cands.head(limit)
    stamp = datetime.now(KST).strftime("%Y%m%d")
    work = ANALYSIS_DIR / f"station_tmap_eta_{stamp}"
    work.mkdir(parents=True, exist_ok=True)
    ckpt = work / "eta_checkpoint.csv"
    latest_csv = OUT_DIR / "station_tmap_eta_latest.csv"
    latest_parquet = OUT_DIR / "station_tmap_eta_latest.parquet"

    done: dict[str, dict] = {}

    def _ingest_resume(path: Path, *, require_real_tmap: bool) -> int:
        if not path.exists():
            return 0
        prev = pd.read_csv(path, dtype={"statId": str})
        n0 = len(done)
        for _, r in prev.iterrows():
            sid = str(r["statId"])
            if require_real_tmap:
                proxy = str(r.get("eta_is_proxy", "")).lower() in {"true", "1", "yes"}
                src = str(r.get("eta_source", ""))
                http = str(r.get("tmap_http", ""))
                eta_ok = pd.notna(r.get("tmap_eta_min")) and str(r.get("tmap_eta_min")) not in {
                    "",
                    "nan",
                    "None",
                }
                real = (not proxy) and eta_ok and (
                    http in {"200", "200.0"} or src.startswith("tmap_routes")
                )
                if not real:
                    continue
            done[sid] = r.to_dict()
        return len(done) - n0

    # Prefer today's ckpt (all rows), then real-TMAP rows from latest/prior ckpts.
    n_ckpt = _ingest_resume(ckpt, require_real_tmap=False)
    n_latest = _ingest_resume(latest_csv, require_real_tmap=True)
    prior_ckpts = sorted(ANALYSIS_DIR.glob("station_tmap_eta_*/eta_checkpoint.csv"))
    n_prior = 0
    for p in prior_ckpts:
        if p.resolve() == ckpt.resolve():
            continue
        n_prior += _ingest_resume(p, require_real_tmap=True)
    print(
        f"resume checkpoint n={len(done)} (today+={n_ckpt}, latest_real+={n_latest}, prior_real+={n_prior})",
        flush=True,
    )

    rows = list(done.values())
    todo = cands.loc[~cands["statId"].astype(str).isin(done)].reset_index(drop=True)
    total = len(cands)
    print(
        f"ETA fetch todo={len(todo)} total={total} origin={ORIGIN['label']}",
        flush=True,
    )

    for i, r in todo.iterrows():
        hv = _haversine_km(
            ORIGIN["lat"], ORIGIN["lng"], float(r["lat"]), float(r["lng"])
        )
        tmap = _tmap_route(
            app_key, ORIGIN["lat"], ORIGIN["lng"], float(r["lat"]), float(r["lng"])
        )
        eta_sec = tmap["eta_seconds"]
        eta_min = round(eta_sec / 60.0, 1) if eta_sec is not None else None
        row = {
            "statId": str(r["statId"]),
            "statNm": r.get("statNm"),
            "lat": float(r["lat"]),
            "lng": float(r["lng"]),
            "origin_id": ORIGIN["id"],
            "origin_label": ORIGIN["label"],
            "origin_lat": ORIGIN["lat"],
            "origin_lng": ORIGIN["lng"],
            "haversine_km": round(hv, 3),
            "haversine_eta_min_proxy": round(hv / ASSUME_SPEED_KMH * 60, 1),
            "tmap_eta_min": eta_min,
            "tmap_eta_minutes_int": int(round(eta_min)) if eta_min is not None else None,
            "tmap_road_km": round(tmap["road_distance_m"] / 1000, 3)
            if tmap["road_distance_m"] is not None
            else None,
            "tmap_http": tmap["http_status"],
            "tmap_error": tmap["error"],
            "fetched_at_kst": datetime.now(KST).isoformat(timespec="seconds"),
            "eta_source": "tmap_routes_trafficInfo_Y",
        }
        rows.append(row)
        n_done = len(rows)
        if n_done % 25 == 0 or n_done == total or (i + 1) == len(todo):
            pd.DataFrame(rows).to_csv(ckpt, index=False, encoding="utf-8-sig")
            print(
                f"[{n_done}/{total}] last={row['statId']} eta={eta_min}",
                flush=True,
            )
        time.sleep(sleep_s)

    df = pd.DataFrame(rows).drop_duplicates(subset=["statId"], keep="last")
    df.to_csv(ckpt, index=False, encoding="utf-8-sig")
    df.to_csv(work / "station_tmap_eta.csv", index=False, encoding="utf-8-sig")
    df.to_csv(latest_csv, index=False, encoding="utf-8-sig")
    df.to_parquet(latest_parquet, index=False)

    ok = int(df["tmap_eta_min"].notna().sum())
    meta = {
        "role": "DA① real TMAP ETA table for public candidates",
        "origin": ORIGIN,
        "n_stations": int(len(df)),
        "tmap_ok": ok,
        "tmap_fail": int(len(df) - ok),
        "eta_min_median": float(df["tmap_eta_min"].median()) if ok else None,
        "eta_min_p50": float(df["tmap_eta_min"].quantile(0.5)) if ok else None,
        "eta_min_p90": float(df["tmap_eta_min"].quantile(0.9)) if ok else None,
        "files": {
            "latest_csv": str(latest_csv.relative_to(REPO)).replace("\\", "/"),
            "latest_parquet": str(latest_parquet.relative_to(REPO)).replace("\\", "/"),
            "work": str(work.relative_to(REPO)).replace("\\", "/"),
        },
        "note": "Serve-time ranking still should re-call TMAP for final 3~5; this table is training/label/input pack.",
    }
    (work / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT_DIR / "station_tmap_eta_latest_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(meta, ensure_ascii=True, indent=2))
    return latest_csv


def _future_tick_map(times: pd.DatetimeIndex, horizon_minutes: int) -> np.ndarray:
    if len(times) == 0:
        return np.array([], dtype=int)
    values = times.astype("datetime64[ns]").view("int64")
    target_values = values + pd.Timedelta(minutes=int(horizon_minutes)).value
    candidates = np.searchsorted(values, target_values, side="left")
    mapping = np.full(len(times), -1, dtype=int)
    segment = (
        times.to_series()
        .diff()
        .gt(pd.Timedelta(minutes=SEGMENT_GAP_MINUTES))
        .cumsum()
        .to_numpy()
    )
    tol = pd.Timedelta(minutes=TARGET_TOLERANCE_MINUTES).value
    for i, j in enumerate(candidates):
        if j >= len(times):
            continue
        if segment[j] != segment[i]:
            continue
        if values[j] - target_values[i] <= tol:
            mapping[i] = int(j)
    return mapping


def build_labels(eta_path: Path | None = None) -> Path:
    eta_path = eta_path or (OUT_DIR / "station_tmap_eta_latest.csv")
    panel_path = OUT_DIR / "station_feature_panel_latest.parquet"
    if not eta_path.exists():
        raise FileNotFoundError(eta_path)
    if not panel_path.exists():
        raise FileNotFoundError(panel_path)

    eta = pd.read_csv(eta_path, dtype={"statId": str})
    eta = eta.loc[eta["tmap_eta_min"].notna()].copy()
    eta["horizon_minutes"] = (
        pd.to_numeric(eta["tmap_eta_minutes_int"], errors="coerce")
        .fillna(pd.to_numeric(eta["tmap_eta_min"], errors="coerce").round())
        .astype(int)
        .clip(lower=1, upper=120)
    )

    panel = pd.read_parquet(panel_path)
    panel["statId"] = panel["statId"].astype(str)
    panel["panel_ts"] = pd.to_datetime(panel["panel_ts"])
    panel = panel.merge(
        eta[["statId", "tmap_eta_min", "horizon_minutes", "origin_id", "haversine_km"]],
        on="statId",
        how="inner",
    )
    if panel.empty:
        raise RuntimeError("panel∩eta empty — rebuild panel or ETA first")

    frames: list[pd.DataFrame] = []
    stats_by_h: list[dict] = []
    for h, g in panel.groupby("horizon_minutes", sort=True):
        # wide-ish per station timeseries
        g = g.sort_values(["statId", "panel_ts"])
        parts = []
        for sid, sg in g.groupby("statId", sort=False):
            times = pd.DatetimeIndex(sg["panel_ts"])
            mapping = _future_tick_map(times, int(h))
            sg = sg.reset_index(drop=True)
            src = np.where(mapping >= 0)[0]
            if not len(src):
                continue
            fut = mapping[src]
            cur_avail = sg.loc[src, "available_count"].to_numpy()
            cur_known = sg.loc[src, "known_chargers"].to_numpy()
            fut_avail = sg.loc[fut, "available_count"].to_numpy()
            fut_known = sg.loc[fut, "known_chargers"].to_numpy()
            # label only when currently known & available candidate, future known
            labelable = (cur_known > 0) & (cur_avail > 0) & (fut_known > 0)
            if not labelable.any():
                continue
            idx = np.where(labelable)[0]
            part = pd.DataFrame(
                {
                    "statId": sid,
                    "feature_as_of": times[src[idx]],
                    "target_time": times[src[idx]] + pd.to_timedelta(int(h), unit="m"),
                    "matched_arrival_time": times[fut[idx]],
                    "horizon_minutes": int(h),
                    "tmap_eta_min": float(sg["tmap_eta_min"].iloc[0]),
                    "haversine_km": float(sg["haversine_km"].iloc[0]),
                    "origin_id": sg["origin_id"].iloc[0],
                    "current_available_count": cur_avail[idx],
                    "arrival_available_count": fut_avail[idx],
                    "target_available_at_arrival": fut_avail[idx] > 0,
                    "label_name": "target_available_at_arrival",
                    "label_definition": "available_count>0 at panel tick nearest as_of+tmap_eta",
                    "eta_source": "tmap_routes",
                }
            )
            parts.append(part)
        if not parts:
            stats_by_h.append(
                {"horizon_minutes": int(h), "labeled_rows": 0, "stations": 0}
            )
            continue
        hf = pd.concat(parts, ignore_index=True)
        frames.append(hf)
        stats_by_h.append(
            {
                "horizon_minutes": int(h),
                "labeled_rows": int(len(hf)),
                "stations": int(hf["statId"].nunique()),
                "positive_rate": float(hf["target_available_at_arrival"].mean()),
            }
        )
        print(
            f"label h={h} rows={len(hf)} stations={hf['statId'].nunique()} "
            f"pos={hf['target_available_at_arrival'].mean():.3f}"
        )

    if not frames:
        raise RuntimeError("no labels produced")

    labels = pd.concat(frames, ignore_index=True)
    stamp = datetime.now(KST).strftime("%Y%m%d")
    out_analysis = ANALYSIS_DIR / f"arrival_labels_tmap_eta_{stamp}"
    out_analysis.mkdir(parents=True, exist_ok=True)
    latest_parquet = OUT_DIR / "arrival_labels_tmap_eta_v1.parquet"
    latest_csv_sample = OUT_DIR / "arrival_labels_tmap_eta_v1_sample.csv"
    labels.to_parquet(latest_parquet, index=False)
    labels.head(50_000).to_csv(latest_csv_sample, index=False, encoding="utf-8-sig")
    labels.to_parquet(out_analysis / "arrival_labels_tmap_eta_v1.parquet", index=False)

    # D1 companion with ETA joined (does not overwrite null-contract main D1 semantics doc)
    d1 = pd.read_csv(
        OUT_DIR / "station_feature_snapshot_latest.csv",
        encoding="utf-8-sig",
        low_memory=False,
    )
    d1["statId"] = d1["statId"].astype(str)
    eta2 = pd.read_csv(eta_path, dtype={"statId": str})
    merged = d1.merge(
        eta2[
            [
                "statId",
                "tmap_eta_min",
                "tmap_eta_minutes_int",
                "tmap_road_km",
                "haversine_km",
                "origin_id",
                "origin_label",
                "fetched_at_kst",
                "eta_source",
            ]
        ],
        on="statId",
        how="left",
    )
    # explicit training columns
    merged["eta_minutes"] = merged["tmap_eta_min"]
    merged["label_ready"] = merged["statId"].isin(labels["statId"].unique())
    with_eta_path = OUT_DIR / "station_feature_snapshot_with_eta_latest.csv"
    merged.to_csv(with_eta_path, index=False, encoding="utf-8-sig")
    merged.to_parquet(OUT_DIR / "station_feature_snapshot_with_eta_latest.parquet", index=False)

    summary = {
        "role": "DA① real TMAP ETA + arrival availability labels",
        "as_of_kst": datetime.now(KST).isoformat(timespec="seconds"),
        "origin": ORIGIN,
        "eta_stations_ok": int(eta["statId"].nunique()),
        "panel_path": str(panel_path.relative_to(REPO)).replace("\\", "/"),
        "panel_range": {
            "min": str(panel["panel_ts"].min()),
            "max": str(panel["panel_ts"].max()),
        },
        "labeled_rows": int(len(labels)),
        "labeled_stations": int(labels["statId"].nunique()),
        "positive_rate": float(labels["target_available_at_arrival"].mean()),
        "by_horizon": stats_by_h,
        "label_column": "target_available_at_arrival",
        "files": {
            "eta_latest": "apps/data-pipeline/evaluation/results/datasets/station_tmap_eta_latest.csv",
            "labels_parquet": "apps/data-pipeline/evaluation/results/datasets/arrival_labels_tmap_eta_v1.parquet",
            "d1_with_eta": "apps/data-pipeline/evaluation/results/datasets/station_feature_snapshot_with_eta_latest.csv",
            "analysis": str(out_analysis.relative_to(REPO)).replace("\\", "/"),
        },
        "contract": {
            "runtime_eta_authority": "backend TMAP on final 3~5 still recommended",
            "d1_main_eta_minutes_null_contract": "main snapshot_latest may stay null; with_eta companion is for ② training",
            "label": "1 if available_count>0 at arrival tick; requires current available>0 candidate filter",
        },
    }
    (out_analysis / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT_DIR / "arrival_labels_tmap_eta_v1_meta.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    share = SHARE / f"ETA_실제_라벨_{stamp}"
    share.mkdir(parents=True, exist_ok=True)
    (share / "data").mkdir(exist_ok=True)
    eta.to_csv(share / "data" / "station_tmap_eta.csv", index=False, encoding="utf-8-sig")
    labels.sample(min(5000, len(labels)), random_state=42).to_csv(
        share / "data" / "arrival_labels_sample.csv", index=False, encoding="utf-8-sig"
    )
    (share / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (share / "README.md").write_text(
        f"""# 실제 TMAP ETA + 도착 가용 라벨 — {stamp}

| 항목 | 값 |
|---|---|
| 출발지 | {ORIGIN['label']} |
| ETA 성공 소 | {summary['eta_stations_ok']} |
| 라벨 행 | {summary['labeled_rows']:,} |
| 라벨 소 | {summary['labeled_stations']} |
| 양성률 (도착 시 가용) | {summary['positive_rate']:.3f} |
| 라벨 컬럼 | `target_available_at_arrival` |

## 파일 (repo)

- ETA: `apps/data-pipeline/evaluation/results/datasets/station_tmap_eta_latest.csv`
- 라벨: `.../arrival_labels_tmap_eta_v1.parquet`
- D1+ETA: `.../station_feature_snapshot_with_eta_latest.csv`

## ② 사용

- 학습 타겟: `target_available_at_arrival`
- 피처 시점: `feature_as_of` (누수 금지: 도착 이후 정보 사용 금지)
- 서빙: 최종 3~5는 BE TMAP 재호출 권장. 이 테이블은 학습·오프라인 평가용 실측 ETA.

```
DA① | real TMAP ETA + arrival labels | {stamp}
```
""",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=True, indent=2))
    return latest_parquet


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eta-only", action="store_true")
    parser.add_argument("--labels-only", action="store_true")
    parser.add_argument("--sleep", type=float, default=0.3)
    parser.add_argument("--limit", type=int, default=None, help="debug limit stations")
    args = parser.parse_args()

    if args.labels_only:
        build_labels()
        return 0
    eta_path = fetch_eta(sleep_s=args.sleep, limit=args.limit)
    if args.eta_only:
        return 0
    build_labels(eta_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
