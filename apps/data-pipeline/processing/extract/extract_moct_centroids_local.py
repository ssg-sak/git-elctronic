"""Extract Daegu link midpoints from a local ITS NODELINKDATA folder (MOCT_LINK.shp).

Example:
  python apps/data-pipeline/processing/extract/extract_moct_centroids_local.py ^
    --shp-dir "D:\\[2026-07-16]NODELINKDATA"

Keeps links that appear in latest loop3 linkspeed (preferred) or LINK_ID prefix 150–159.
Writes docs/data/extracted/its_nodelink/daegu_std_link_centroids_latest.csv
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import pandas as pd
import shapefile
from pyproj import Transformer

_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))
from _bootstrap import ensure_paths

REPO = ensure_paths()
OUT = REPO / "docs/data/extracted/its_nodelink"
SRC_EPSG = 5186
DST_EPSG = 4326
DAEGU_PREFIX_LO = 150
DAEGU_PREFIX_HI = 159


def _latest_linkspeed_ids() -> set[str]:
    loop3 = REPO / "docs/data/loops/loop3"
    files = sorted(loop3.glob("*/daegu_traffic_linkspeed_*.csv"))
    files = [p for p in files if "latest" not in p.name]
    if not files:
        return set()
    df = pd.read_csv(files[-1], dtype=str, usecols=["linkId"])
    return set(df["linkId"].dropna().astype(str))


def _midpoint_xy(points: list[tuple[float, float]]) -> tuple[float, float]:
    if not points:
        return (float("nan"), float("nan"))
    if len(points) == 1:
        return points[0]
    seg = [0.0]
    for i in range(1, len(points)):
        x0, y0 = points[i - 1]
        x1, y1 = points[i]
        seg.append(seg[-1] + math.hypot(x1 - x0, y1 - y0))
    half = seg[-1] / 2.0
    if half <= 0:
        return points[len(points) // 2]
    for i in range(1, len(seg)):
        if seg[i] >= half:
            t = 0.0 if seg[i] == seg[i - 1] else (half - seg[i - 1]) / (seg[i] - seg[i - 1])
            x0, y0 = points[i - 1]
            x1, y1 = points[i]
            return (x0 + t * (x1 - x0), y0 + t * (y1 - y0))
    return points[-1]


def extract(shp_dir: Path) -> dict:
    link_shp = shp_dir / "MOCT_LINK.shp"
    if not link_shp.is_file():
        hits = list(shp_dir.rglob("MOCT_LINK.shp"))
        if not hits:
            raise FileNotFoundError(f"MOCT_LINK.shp not under {shp_dir}")
        link_shp = hits[0]

    live = _latest_linkspeed_ids()
    r = shapefile.Reader(str(link_shp.with_suffix("")))
    fields = [f[0] for f in r.fields[1:]]
    if "LINK_ID" not in fields:
        raise KeyError(f"LINK_ID missing; fields={fields}")
    id_i = fields.index("LINK_ID")

    prj = link_shp.with_suffix(".prj")
    src = SRC_EPSG
    if prj.is_file():
        txt = prj.read_text(encoding="utf-8", errors="replace")
        if "5186" in txt or "Central_Belt_2010" in txt:
            src = 5186
    transformer = Transformer.from_crs(src, DST_EPSG, always_xy=True)

    rows: list[dict] = []
    n_all = 0
    n_live_hit = 0
    for shape_rec in r.iterShapeRecords():
        n_all += 1
        if n_all % 200_000 == 0:
            print(f"  scanned {n_all:,} links · kept {len(rows):,}", flush=True)
        link_id = str(shape_rec.record[id_i]).strip()
        if len(link_id) < 3:
            continue
        in_live = link_id in live if live else False
        try:
            prefix = int(link_id[:3])
        except ValueError:
            continue
        keep = in_live or (DAEGU_PREFIX_LO <= prefix <= DAEGU_PREFIX_HI)
        if not keep:
            continue
        if in_live:
            n_live_hit += 1
        pts = [(float(x), float(y)) for x, y in (shape_rec.shape.points or [])]
        mx, my = _midpoint_xy(pts)
        lng, lat = transformer.transform(mx, my)
        rows.append(
            {
                "linkId": link_id,
                "lng": round(lng, 7),
                "lat": round(lat, 7),
                "geom_source": "moct_link_shp",
            }
        )

    OUT.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows).drop_duplicates(subset=["linkId"], keep="first")
    # Prefer live-only subset for join quality when available
    if live:
        live_df = df[df["linkId"].isin(live)].copy()
        if not live_df.empty:
            df_out = live_df
        else:
            df_out = df
    else:
        df_out = df

    csv_path = OUT / "daegu_std_link_centroids_latest.csv"
    df_out.to_csv(csv_path, index=False, encoding="utf-8-sig")
    df.to_csv(OUT / "daegu_std_link_centroids_prefix150.csv", index=False, encoding="utf-8-sig")

    overlap = len(set(df_out["linkId"]) & live) if live else 0
    meta = {
        "source_dir": str(shp_dir),
        "link_shp": str(link_shp),
        "src_epsg": src,
        "crs_out": f"EPSG:{DST_EPSG}",
        "n_links_national_scanned": n_all,
        "n_links_daegu_or_live": int(len(df)),
        "n_links_exported": int(len(df_out)),
        "linkspeed_unique_ids": len(live),
        "linkspeed_id_overlap": overlap,
        "linkspeed_overlap_rate": round(overlap / len(live), 4) if live else None,
        "n_live_hits_while_scan": n_live_hit,
        "outputs": {
            "centroids_csv": str(csv_path.relative_to(REPO)).replace("\\", "/"),
        },
    }
    (OUT / "meta_moct_extract.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return meta


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--shp-dir",
        type=Path,
        default=Path(r"D:\[2026-07-16]NODELINKDATA"),
        help="Folder containing MOCT_LINK.shp",
    )
    args = ap.parse_args()
    if not args.shp_dir.is_dir():
        print(f"FAIL: not a directory: {args.shp_dir}")
        return 1
    meta = extract(args.shp_dir)
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    return 0 if (meta.get("linkspeed_id_overlap") or 0) > 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
