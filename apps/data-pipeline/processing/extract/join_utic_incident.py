"""Join charger stations ↔ UTIC Daegu incidents (nearest within radius).

Input:  docs/data/loops/loop2/daegu_traffic_incident_utic_latest.csv
Output: docs/data/spatial_join/join_traffic_incident_utic_1000m.csv

Attribution: 경찰청 도시교통정보센터(UTIC)
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pandas as pd

import sys
from pathlib import Path
_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))
from _bootstrap import ensure_paths

REPO = ensure_paths()
from loop_paths import loop2_dir

MASTER = (
    REPO
    / "apps/data-pipeline/evaluation/personal/experiments"
    / "SANDBOX_20260716_preprocess_pipeline"
    / "data/processed/charger_master.csv"
)
INCIDENT = loop2_dir() / "daegu_traffic_incident_utic_latest.csv"
OUT_DIR = REPO / "docs/data/spatial_join"
RADIUS_M = 1000


def haversine_m(lat1, lng1, lat2, lng2) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def load_stations() -> pd.DataFrame:
    df = pd.read_csv(MASTER, dtype=str, low_memory=False)
    for c in ("lat_num", "lng_num", "lat", "lng"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    lat = df["lat_num"] if "lat_num" in df.columns else df["lat"]
    lng = df["lng_num"] if "lng_num" in df.columns else df["lng"]
    df = df.assign(lat_f=lat, lng_f=lng)
    if "coordinate_quality_flag" in df.columns:
        df = df[df["coordinate_quality_flag"] == "OK"]
    return (
        df.dropna(subset=["lat_f", "lng_f"])
        .drop_duplicates(subset=["statId"])
        [["statId", "statNm", "addr", "lat_f", "lng_f"]]
        .reset_index(drop=True)
    )


def load_incidents() -> pd.DataFrame:
    if not INCIDENT.exists():
        raise FileNotFoundError(f"Run extract_utic_incident.py first: {INCIDENT}")
    df = pd.read_csv(INCIDENT, dtype=str)
    df["lat"] = pd.to_numeric(df["locationDataY"], errors="coerce")
    df["lng"] = pd.to_numeric(df["locationDataX"], errors="coerce")
    return df.dropna(subset=["lat", "lng"]).reset_index(drop=True)


def nearest_join(stations: pd.DataFrame, pois: pd.DataFrame, radius_m: float) -> pd.DataFrame:
    rows = []
    poi_coords = list(
        zip(
            pois["incidentId"].astype(str),
            pois["incidentTitle"].astype(str),
            pois["lat"].astype(float),
            pois["lng"].astype(float),
            strict=True,
        )
    )
    for _, s in stations.iterrows():
        best_id = best_name = None
        best_d = None
        for iid, title, plat, plng in poi_coords:
            d = haversine_m(float(s["lat_f"]), float(s["lng_f"]), plat, plng)
            if d <= radius_m and (best_d is None or d < best_d):
                best_d = d
                best_id = iid
                best_name = title[:80]
        rows.append(
            {
                "statId": s["statId"],
                "statNm": s["statNm"],
                "matched_id": best_id or "",
                "matched_name": best_name or "",
                "distance_m": round(best_d, 1) if best_d is not None else "",
                "radius_m": radius_m,
                "matched": best_d is not None,
                "traffic_source": "utic",
            }
        )
    return pd.DataFrame(rows)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stations = load_stations()
    incidents = load_incidents()
    joined = nearest_join(stations, incidents, RADIUS_M)

    out_path = OUT_DIR / f"join_traffic_incident_utic_{RADIUS_M}m.csv"
    latest = OUT_DIR / "join_traffic_incident_utic_1000m.csv"
    joined.to_csv(out_path, index=False, encoding="utf-8-sig")
    joined.to_csv(latest, index=False, encoding="utf-8-sig")

    matched_n = int(joined["matched"].sum())
    meta = {
        "layer": "traffic_incident_utic",
        "radius_m": RADIUS_M,
        "stations": int(len(joined)),
        "incidents": int(len(incidents)),
        "matched": matched_n,
        "match_rate": round(matched_n / len(joined), 4) if len(joined) else 0,
        "attribution": "경찰청 도시교통정보센터(UTIC)",
        "output": str(latest.relative_to(REPO)).replace("\\", "/"),
    }
    (OUT_DIR / "join_traffic_incident_utic_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
