"""Finalize ETA table after partial TMAP fetch + build arrival labels.

- Keep real TMAP rows (http 200)
- Fill QUOTA/fail rows with distance-band calibration proxy
- Build arrival labels from panel using per-station horizon
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from build_station_eta_and_labels import (  # noqa: E402
    ANALYSIS_DIR,
    ASSUME_SPEED_KMH,
    ORIGIN,
    OUT_DIR,
    SHARE,
    _haversine_km,
    _load_candidates,
    build_labels,
)

KST = ZoneInfo("Asia/Seoul")
REPO = OUT_DIR.parents[4]


def _band_ratio(km: float, bands: pd.DataFrame, global_ratio: float) -> float:
    for _, r in bands.iterrows():
        if pd.isna(r.get("ratio_median")):
            continue
        if float(r["haversine_km_lo"]) <= km < float(r["haversine_km_hi"]):
            return float(r["ratio_median"])
    return float(global_ratio)


def main() -> int:
    stamp = datetime.now(KST).strftime("%Y%m%d")
    ckpt = ANALYSIS_DIR / f"station_tmap_eta_{stamp}" / "eta_checkpoint.csv"
    if not ckpt.exists():
        # fallback latest work dir
        dirs = sorted(ANALYSIS_DIR.glob("station_tmap_eta_*"))
        if not dirs:
            raise FileNotFoundError("no station_tmap_eta_* checkpoint")
        ckpt = dirs[-1] / "eta_checkpoint.csv"
    cal_path = ANALYSIS_DIR / f"eta_calibration_{stamp}" / "calibration.json"
    if not cal_path.exists():
        cals = sorted(ANALYSIS_DIR.glob("eta_calibration_*/calibration.json"))
        cal_path = cals[-1] if cals else None

    partial = pd.read_csv(ckpt, dtype={"statId": str})
    cands = _load_candidates()
    cands["statId"] = cands["statId"].astype(str)

    global_ratio = 1.94
    bands = pd.DataFrame()
    if cal_path and cal_path.exists():
        cal = json.loads(cal_path.read_text(encoding="utf-8"))
        global_ratio = float(cal.get("ratio_tmap_over_haversine_median") or global_ratio)
        bands = pd.DataFrame(cal.get("ratio_by_band") or [])

    # index partial
    by_id = {str(r.statId): r for r in partial.itertuples(index=False)}
    rows = []
    for r in cands.itertuples(index=False):
        sid = str(r.statId)
        hv = _haversine_km(ORIGIN["lat"], ORIGIN["lng"], float(r.lat), float(r.lng))
        prev = by_id.get(sid)
        if prev is not None and pd.notna(getattr(prev, "tmap_eta_min", None)):
            rows.append(
                {
                    "statId": sid,
                    "statNm": getattr(prev, "statNm", r.statNm),
                    "lat": float(r.lat),
                    "lng": float(r.lng),
                    "origin_id": ORIGIN["id"],
                    "origin_label": ORIGIN["label"],
                    "origin_lat": ORIGIN["lat"],
                    "origin_lng": ORIGIN["lng"],
                    "haversine_km": round(hv, 3),
                    "haversine_eta_min_proxy": round(hv / ASSUME_SPEED_KMH * 60, 1),
                    "tmap_eta_min": float(prev.tmap_eta_min),
                    "tmap_eta_minutes_int": int(round(float(prev.tmap_eta_min))),
                    "tmap_road_km": getattr(prev, "tmap_road_km", None),
                    "tmap_http": getattr(prev, "tmap_http", 200),
                    "tmap_error": None,
                    "fetched_at_kst": getattr(prev, "fetched_at_kst", None),
                    "eta_source": "tmap_routes_trafficInfo_Y",
                    "eta_is_proxy": False,
                }
            )
            continue
        ratio = _band_ratio(hv, bands, global_ratio) if len(bands) else global_ratio
        eta = round(hv / ASSUME_SPEED_KMH * 60 * ratio, 1)
        rows.append(
            {
                "statId": sid,
                "statNm": r.statNm,
                "lat": float(r.lat),
                "lng": float(r.lng),
                "origin_id": ORIGIN["id"],
                "origin_label": ORIGIN["label"],
                "origin_lat": ORIGIN["lat"],
                "origin_lng": ORIGIN["lng"],
                "haversine_km": round(hv, 3),
                "haversine_eta_min_proxy": round(hv / ASSUME_SPEED_KMH * 60, 1),
                "tmap_eta_min": eta,
                "tmap_eta_minutes_int": int(max(1, round(eta))),
                "tmap_road_km": None,
                "tmap_http": getattr(prev, "tmap_http", None) if prev is not None else None,
                "tmap_error": getattr(prev, "tmap_error", "filled_by_calibration")
                if prev is not None
                else "no_tmap_call",
                "fetched_at_kst": datetime.now(KST).isoformat(timespec="seconds"),
                "eta_source": "haversine_x_band_calibration",
                "eta_is_proxy": True,
                "calibration_ratio": ratio,
            }
        )

    df = pd.DataFrame(rows)
    work = ANALYSIS_DIR / f"station_tmap_eta_{stamp}"
    work.mkdir(parents=True, exist_ok=True)
    latest_csv = OUT_DIR / "station_tmap_eta_latest.csv"
    df.to_csv(latest_csv, index=False, encoding="utf-8-sig")
    df.to_parquet(OUT_DIR / "station_tmap_eta_latest.parquet", index=False)
    df.to_csv(work / "station_tmap_eta_final.csv", index=False, encoding="utf-8-sig")

    n_real = int((~df["eta_is_proxy"]).sum())
    n_proxy = int(df["eta_is_proxy"].sum())
    meta = {
        "as_of_kst": datetime.now(KST).isoformat(timespec="seconds"),
        "origin": ORIGIN,
        "n_stations": int(len(df)),
        "eta_real_tmap": n_real,
        "eta_proxy_calibrated": n_proxy,
        "tmap_quota_note": "Partial TMAP fetch hit HTTP 429 QUOTA_EXCEEDED; remainder filled by band calibration",
        "calibration_file": str(cal_path.relative_to(REPO)).replace("\\", "/")
        if cal_path
        else None,
        "files": {
            "latest_csv": str(latest_csv.relative_to(REPO)).replace("\\", "/"),
        },
    }
    (OUT_DIR / "station_tmap_eta_latest_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (work / "final_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(meta, ensure_ascii=True, indent=2), flush=True)

    # labels use tmap_eta_min / int for all rows (real+proxy)
    build_labels(latest_csv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
