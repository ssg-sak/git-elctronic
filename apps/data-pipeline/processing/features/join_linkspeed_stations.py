"""Nearest linkspeed join: station ↔ TMAP/ITS link midpoint (additive features).

Reads:
  - D1 or charger service coords
  - daegu_link_centroids_tmap_latest.csv
  - latest loop3 linkspeed snapshot

Writes:
  docs/data/spatial_join/join_linkspeed_nearest.csv
  docs/data/spatial_join/join_linkspeed_nearest_meta.json

Columns (station grain):
  nearest_link_id, nearest_link_m, link_speed_kph, link_cong_grade, link_cong_grade_nm

Rules:
  - Max match distance MAX_M (default 400m). Beyond → null (do not invent).
  - Not route ETA. City/link context only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))
from _bootstrap import ensure_paths

REPO = ensure_paths()
SPATIAL = REPO / "docs/data/spatial_join"
SHP_CENTROIDS = REPO / "docs/data/extracted/its_nodelink/daegu_std_link_centroids_latest.csv"
TMAP_CENTROIDS = REPO / "docs/data/extracted/its_nodelink/daegu_link_centroids_tmap_latest.csv"
OUT_CSV = SPATIAL / "join_linkspeed_nearest.csv"
OUT_META = SPATIAL / "join_linkspeed_nearest_meta.json"
MAX_M = 400.0


def _centroids_path() -> Path:
    """Prefer official MOCT_LINK midpoints; fall back to TMAP node midpoints."""
    if SHP_CENTROIDS.is_file():
        return SHP_CENTROIDS
    if TMAP_CENTROIDS.is_file():
        return TMAP_CENTROIDS
    raise FileNotFoundError(
        f"missing centroids: tried {SHP_CENTROIDS.name} and {TMAP_CENTROIDS.name}"
    )


def _haversine_m(lat1, lng1, lat2, lng2):
    r = 6371000.0
    p1 = np.radians(lat1)
    p2 = np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlmb = np.radians(lng2 - lng1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlmb / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


def _stations() -> pd.DataFrame:
    d1 = REPO / "apps/data-pipeline/evaluation/results/datasets/station_feature_snapshot_latest.csv"
    if d1.is_file():
        df = pd.read_csv(d1, dtype=str, low_memory=False)
        src = str(d1.relative_to(REPO)).replace("\\", "/")
    else:
        info = REPO / "docs/data/extracted/charger/info/daegu_charger_info_service_latest.csv"
        df = pd.read_csv(info, dtype=str, low_memory=False)
        src = str(info.relative_to(REPO)).replace("\\", "/")
    for c in ("lat", "lng"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    if "coord_ok" in df.columns:
        ok = df["coord_ok"].astype(str).str.lower().isin(["true", "1"])
        df = df.loc[ok]
    df = df.dropna(subset=["lat", "lng"]).drop_duplicates("statId")
    return df[["statId", "lat", "lng"]].copy(), src


def _latest_linkspeed() -> Path:
    loop3 = REPO / "docs/data/loops/loop3"
    files = sorted(loop3.glob("*/daegu_traffic_linkspeed_*.csv"))
    files = [p for p in files if "latest" not in p.name]
    if not files:
        raise FileNotFoundError("no linkspeed")
    return files[-1]


def main() -> int:
    try:
        centroids_path = _centroids_path()
    except FileNotFoundError as e:
        print(f"FAIL: {e} — run extract_moct_centroids_local.py or build_link_centroids_tmap.py")
        return 1

    stations, station_src = _stations()
    cents = pd.read_csv(centroids_path, dtype=str)
    cents["lat"] = pd.to_numeric(cents["lat"], errors="coerce")
    cents["lng"] = pd.to_numeric(cents["lng"], errors="coerce")
    cents = cents.dropna(subset=["lat", "lng", "linkId"]).drop_duplicates("linkId")
    if cents.empty:
        print("FAIL: no geocoded link centroids")
        return 2

    speed_path = _latest_linkspeed()
    speed = pd.read_csv(speed_path, dtype=str)
    speed["speedKph"] = pd.to_numeric(speed.get("speedKph"), errors="coerce")
    speed["congGrade"] = pd.to_numeric(speed.get("congGrade"), errors="coerce")
    speed = speed.drop_duplicates("linkId", keep="first")
    keep_speed = ["linkId", "speedKph", "congGrade", "congGradeNm", "roadName", "atmsTm", "fetchedAt"]
    keep_speed = [c for c in keep_speed if c in speed.columns]
    cents = cents.merge(speed[keep_speed], on="linkId", how="inner")
    if cents.empty:
        print("FAIL: no overlap between centroids and linkspeed")
        return 3

    s_lat = stations["lat"].to_numpy(dtype=float)
    s_lng = stations["lng"].to_numpy(dtype=float)
    l_lat = cents["lat"].to_numpy(dtype=float)
    l_lng = cents["lng"].to_numpy(dtype=float)

    # Chunk stations to keep memory modest (N_stations × N_links)
    best_idx = np.full(len(stations), -1, dtype=int)
    best_dist = np.full(len(stations), np.inf, dtype=float)
    chunk = 250
    for start in range(0, len(stations), chunk):
        end = min(start + chunk, len(stations))
        # (chunk, links)
        d = _haversine_m(
            s_lat[start:end, None],
            s_lng[start:end, None],
            l_lat[None, :],
            l_lng[None, :],
        )
        idx = np.argmin(d, axis=1)
        dist = d[np.arange(end - start), idx]
        best_idx[start:end] = idx
        best_dist[start:end] = dist

    matched = best_dist <= MAX_M
    out = stations.copy()
    out["nearest_link_m"] = np.where(matched, np.round(best_dist, 1), np.nan)
    pick = cents.iloc[np.clip(best_idx, 0, len(cents) - 1)].reset_index(drop=True)
    out["nearest_link_id"] = np.where(matched, pick["linkId"].to_numpy(), None)
    out["link_speed_kph"] = np.where(matched, pick["speedKph"].to_numpy(), np.nan)
    out["link_cong_grade"] = np.where(matched, pick["congGrade"].to_numpy(), np.nan)
    if "congGradeNm" in pick.columns:
        out["link_cong_grade_nm"] = np.where(matched, pick["congGradeNm"].to_numpy(), None)
    else:
        out["link_cong_grade_nm"] = None

    SPATIAL.mkdir(parents=True, exist_ok=True)
    cols = [
        "statId",
        "nearest_link_id",
        "nearest_link_m",
        "link_speed_kph",
        "link_cong_grade",
        "link_cong_grade_nm",
    ]
    out[cols].to_csv(OUT_CSV, index=False, encoding="utf-8-sig")

    meta = {
        "max_match_m": MAX_M,
        "station_source": station_src,
        "centroids_source": str(centroids_path.relative_to(REPO)).replace("\\", "/"),
        "linkspeed_source": str(speed_path.relative_to(REPO)).replace("\\", "/"),
        "n_link_centroids_with_speed": int(len(cents)),
        "n_stations": int(len(out)),
        "n_matched": int(matched.sum()),
        "match_rate": round(float(matched.mean()), 4),
        "median_nearest_link_m": float(np.nanmedian(out["nearest_link_m"])),
        "outputs": {"csv": str(OUT_CSV.relative_to(REPO)).replace("\\", "/")},
        "contract": "auxiliary link context - not route ETA",
    }
    OUT_META.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        print(json.dumps(meta, ensure_ascii=False, indent=2))
    except UnicodeEncodeError:
        print(json.dumps(meta, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
