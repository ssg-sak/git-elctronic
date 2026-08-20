"""Download ITS national standard node/link and extract Daegu link centroids.

Uses curl.exe for HTTPS (Python SSL trust store fails on its.go.kr here).
Parses MOCT_LINK.shp with pyshp + pyproj (no geopandas required).

Daegu ITS linkspeed STD_LINK_ID ≈ 150xxxxxxx → keep LINK_ID prefix 150–159.
"""
from __future__ import annotations

import json
import math
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

import shapefile  # pyshp
from pyproj import Transformer

_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))
from _bootstrap import ensure_paths

# Same-directory helper (processing/ is on sys.path, not necessarily extract/)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _its_curl_fetch import download_file, fetch_csrf_and_cookie, list_files  # noqa: E402

REPO = ensure_paths()
OUT = REPO / "docs/data/extracted/its_nodelink"

DAEGU_PREFIX_LO = 150
DAEGU_PREFIX_HI = 159
# ITS MOCT historically Korea 2000 / Central Belt 2010
SRC_EPSG = 5186
DST_EPSG = 4326


def _latest_linkspeed_ids() -> set[str]:
    import pandas as pd

    loop3 = REPO / "docs/data/loops/loop3"
    files = sorted(loop3.glob("*/daegu_traffic_linkspeed_*.csv"))
    files = [p for p in files if "latest" not in p.name]
    if not files:
        latest = REPO / "docs/data/loops/daegu_traffic/daegu_traffic_linkspeed_latest.csv"
        files = [latest] if latest.is_file() else []
    if not files:
        return set()
    df = pd.read_csv(files[-1], dtype=str, usecols=["linkId"])
    return set(df["linkId"].dropna().astype(str))


def _find_shp(root: Path, name: str) -> Path:
    hits = list(root.rglob(name))
    if not hits:
        raise FileNotFoundError(f"{name} not found under {root}")
    return hits[0]


def _midpoint_xy(points: list[tuple[float, float]]) -> tuple[float, float]:
    if not points:
        return (float("nan"), float("nan"))
    if len(points) == 1:
        return points[0]
    # cumulative length along polyline → half
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


def extract_daegu_centroids(zip_path: Path, out_dir: Path) -> dict:
    import pandas as pd

    unpack = out_dir / "_unpack"
    if unpack.exists():
        shutil.rmtree(unpack)
    unpack.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(unpack)

    link_shp = _find_shp(unpack, "MOCT_LINK.shp")
    # pyshp wants path without extension
    r = shapefile.Reader(str(link_shp.with_suffix("")))
    fields = [f[0] for f in r.fields[1:]]
    if "LINK_ID" not in fields:
        raise KeyError(f"LINK_ID missing; fields={fields}")
    id_i = fields.index("LINK_ID")

    # Try CRS from .prj; fallback EPSG:5186
    prj = link_shp.with_suffix(".prj")
    src = SRC_EPSG
    if prj.is_file():
        prj_txt = prj.read_text(encoding="utf-8", errors="replace")
        if "Central_Belt_2010" in prj_txt or "5186" in prj_txt:
            src = 5186
        elif "Korea_2000" in prj_txt and "Central" in prj_txt:
            src = 5186
    transformer = Transformer.from_crs(src, DST_EPSG, always_xy=True)

    live = _latest_linkspeed_ids()
    rows: list[dict] = []
    n_all = 0
    for shape_rec in r.iterShapeRecords():
        n_all += 1
        link_id = str(shape_rec.record[id_i]).strip()
        if len(link_id) < 3:
            continue
        try:
            prefix = int(link_id[:3])
        except ValueError:
            continue
        keep = DAEGU_PREFIX_LO <= prefix <= DAEGU_PREFIX_HI
        if not keep and live and link_id in live:
            keep = True
        if not keep:
            continue
        pts = [(float(x), float(y)) for x, y in (shape_rec.shape.points or [])]
        mx, my = _midpoint_xy(pts)
        lng, lat = transformer.transform(mx, my)
        rows.append({"linkId": link_id, "lng": round(lng, 7), "lat": round(lat, 7)})

    df = pd.DataFrame(rows).drop_duplicates(subset=["linkId"], keep="first")
    csv_path = out_dir / "daegu_std_link_centroids_latest.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")

    meta = {
        "source": "its.go.kr nodelink",
        "zip": zip_path.name,
        "link_shp": str(link_shp.relative_to(unpack)).replace("\\", "/"),
        "src_epsg": src,
        "crs_out": f"EPSG:{DST_EPSG}",
        "daegu_prefix_range": [DAEGU_PREFIX_LO, DAEGU_PREFIX_HI],
        "n_links_national_loaded": n_all,
        "n_links_daegu_filter": int(len(df)),
        "outputs": {
            "centroids_csv": str(csv_path.relative_to(REPO)).replace("\\", "/"),
        },
    }
    return meta


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    cookie_jar = Path(tempfile.gettempdir()) / "its_nodelink_cookies.txt"
    csrf = fetch_csrf_and_cookie(cookie_jar)
    print(f"csrf ok len={len(csrf)}")

    files: list[dict] = []
    for st in (90, 30, 7, 0, -1):
        try:
            files = list_files(cookie_jar, csrf, search_type=st)
            print(f"list searchType={st} n={len(files)}")
            if files:
                break
        except Exception as e:
            print(f"list fail searchType={st}: {e}")

    if not files:
        print("FAIL: no node-link files listed")
        return 1

    preferred = [f for f in files if "NODELINK" in str(f.get("fileId", "")).upper()]
    pick = (preferred or files)[0]
    file_id = str(pick["fileId"])
    print(f"download {file_id} size={pick.get('fileSize')}")

    zip_path = OUT / "NODELINKDATA_latest.zip"
    download_file(cookie_jar, csrf, file_id, zip_path)
    print(f"OK zip bytes={zip_path.stat().st_size}")

    (OUT / "meta_download.json").write_text(
        json.dumps(
            {"fileId": file_id, "fileSize": pick.get("fileSize"), "zip": zip_path.name},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    meta = extract_daegu_centroids(zip_path, OUT)
    live = _latest_linkspeed_ids()
    mapped = set(
        __import__("pandas")
        .read_csv(OUT / "daegu_std_link_centroids_latest.csv", dtype=str)["linkId"]
    )
    hit = len(live & mapped) if live else 0
    meta["linkspeed_unique_ids"] = len(live)
    meta["linkspeed_id_overlap"] = hit
    meta["linkspeed_overlap_rate"] = round(hit / len(live), 4) if live else None
    (OUT / "meta_extract.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    return 0 if (not live or hit > 0) else 3


if __name__ == "__main__":
    raise SystemExit(main())
