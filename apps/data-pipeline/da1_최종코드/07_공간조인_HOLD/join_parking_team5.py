# -*- coding: utf-8 -*-
"""DA①: charger stations ↔ team_5 parking spatial join (1 km).

Writes:
  docs/data/spatial_join/join_parking_team5_1000m.csv
  docs/data/spatial_join/join_parking_team5_meta.json

Does NOT set recommendation scores (②).
"""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))
from _bootstrap import ensure_paths

REPO = ensure_paths()
from loop_paths import EXTRACTED_CHARGER_INFO, EXTRACTED_PARKING

KST = ZoneInfo("Asia/Seoul")
OUT_DIR = REPO / "docs" / "data" / "spatial_join"
RADIUS_M = 1000.0


def haversine_m_vec(
    lat1: np.ndarray, lng1: np.ndarray, lat2: np.ndarray, lng2: np.ndarray
) -> np.ndarray:
    r = 6371000.0
    p1 = np.radians(lat1)
    p2 = np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dl = np.radians(lng2 - lng1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def load_stations() -> pd.DataFrame:
    path = EXTRACTED_CHARGER_INFO / "daegu_charger_info_service_latest.csv"
    df = pd.read_csv(path, dtype=str, low_memory=False)
    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    df["lng"] = pd.to_numeric(df["lng"], errors="coerce")
    st = (
        df.dropna(subset=["lat", "lng"])
        .drop_duplicates(subset=["statId"], keep="first")
        [["statId", "statNm", "addr", "lat", "lng"]]
        .reset_index(drop=True)
    )
    return st


def load_parking() -> pd.DataFrame:
    info = pd.read_csv(
        EXTRACTED_PARKING / "daegu_parking_info_team5_latest.csv", dtype=str
    )
    info["lat"] = pd.to_numeric(info["lat"], errors="coerce")
    info["lng"] = pd.to_numeric(info["lng"], errors="coerce")
    info = info.dropna(subset=["lat", "lng", "pkltId"]).drop_duplicates("pkltId")

    rt_path = EXTRACTED_PARKING / "daegu_parking_realtime_team5_latest.csv"
    rt = pd.read_csv(rt_path, dtype=str) if rt_path.is_file() else pd.DataFrame()
    if len(rt) and "pkltId" in rt.columns:
        keep = [
            c
            for c in [
                "pkltId",
                "congestion_status",
                "total_spaces",
                "remaining_spaces",
                "occupied_spaces",
                "occupancy_rate",
                "fetchedAt",
            ]
            if c in rt.columns
        ]
        info = info.merge(rt[keep], on="pkltId", how="left", suffixes=("", "_rt"))
    info["parking_source"] = "team5_pis"
    info["has_realtime"] = info["remaining_spaces"].notna() if "remaining_spaces" in info.columns else False
    return info.reset_index(drop=True)


def nearest_parking(stations: pd.DataFrame, parking: pd.DataFrame) -> pd.DataFrame:
    s_lat = stations["lat"].to_numpy(dtype=float)
    s_lng = stations["lng"].to_numpy(dtype=float)
    p_lat = parking["lat"].to_numpy(dtype=float)
    p_lng = parking["lng"].to_numpy(dtype=float)

    # chunk stations to limit memory (N_s * N_p)
    chunk = 400
    best_idx = np.full(len(stations), -1, dtype=int)
    best_d = np.full(len(stations), np.inf, dtype=float)

    for start in range(0, len(stations), chunk):
        end = min(start + chunk, len(stations))
        # (chunk, n_park)
        d = haversine_m_vec(
            s_lat[start:end, None],
            s_lng[start:end, None],
            p_lat[None, :],
            p_lng[None, :],
        )
        j = np.argmin(d, axis=1)
        dist = d[np.arange(end - start), j]
        best_idx[start:end] = j
        best_d[start:end] = dist

    rows = []
    for i in range(len(stations)):
        s = stations.iloc[i]
        j = int(best_idx[i])
        dist = float(best_d[i])
        matched = bool(j >= 0 and dist <= RADIUS_M and math.isfinite(dist))
        if matched:
            p = parking.iloc[j]
            rows.append(
                {
                    "statId": s["statId"],
                    "statNm": s["statNm"],
                    "matched_id": p["pkltId"],
                    "matched_name": p.get("pkltNm"),
                    "distance_m": round(dist, 1),
                    "radius_m": RADIUS_M,
                    "matched": True,
                    "remaining_spaces": p.get("remaining_spaces"),
                    "total_spaces": p.get("total_spaces"),
                    "occupancy_rate": p.get("occupancy_rate"),
                    "congestion_status": p.get("congestion_status"),
                    "has_realtime": bool(p.get("has_realtime")),
                    "parking_lat": p["lat"],
                    "parking_lng": p["lng"],
                    "parking_source": "team5_pis",
                }
            )
        else:
            rows.append(
                {
                    "statId": s["statId"],
                    "statNm": s["statNm"],
                    "matched_id": None,
                    "matched_name": None,
                    "distance_m": None,
                    "radius_m": RADIUS_M,
                    "matched": False,
                    "remaining_spaces": None,
                    "total_spaces": None,
                    "occupancy_rate": None,
                    "congestion_status": None,
                    "has_realtime": False,
                    "parking_lat": None,
                    "parking_lng": None,
                    "parking_source": "team5_pis",
                }
            )
    return pd.DataFrame(rows)


def main() -> int:
    as_of = datetime.now(KST)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    stations = load_stations()
    parking = load_parking()
    print(f"stations={len(stations)} parking_with_coords={len(parking)} realtime_flag={int(parking['has_realtime'].sum())}")

    join = nearest_parking(stations, parking)
    out_csv = OUT_DIR / "join_parking_team5_1000m.csv"
    join.to_csv(out_csv, index=False, encoding="utf-8-sig")

    matched = int(join["matched"].sum())
    with_rt = int((join["matched"] & join["has_realtime"]).sum())
    meta = {
        "as_of_kst": as_of.isoformat(timespec="seconds"),
        "radius_m": RADIUS_M,
        "stations": len(stations),
        "parking_pois": len(parking),
        "matched_within_radius": matched,
        "match_rate": round(matched / len(stations), 4) if len(stations) else 0,
        "matched_with_realtime": with_rt,
        "parking_source": "team5_pis",
        "parking_is_mock": False,
        "role": "DA① spatial join (no scores)",
        "output": str(out_csv.relative_to(REPO)).replace("\\", "/"),
        "note": "full Team5 parking_lot_info export (1,764 lots); unmatched stations remain null.",
    }
    meta_path = OUT_DIR / "join_parking_team5_meta.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False, indent=2), flush=True)

    # remove obsolete mock join
    mock = OUT_DIR / "join_parking_mock_1000m.csv"
    if mock.is_file():
        mock.unlink()
        print("deleted", mock.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
