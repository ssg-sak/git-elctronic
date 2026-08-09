"""Build Daegu ITS link midpoints via TMAP POI geocode of start/end node names.

Why: linkspeed API has STD_LINK_ID but no lat/lng. Official ITS MOCT_LINK zip
download is blocked for non-browser clients (HTTP 307 + contact message).
Unique node names in one tick ≈ 150 — cheap one-shot with cache.

Outputs:
  docs/data/extracted/its_nodelink/daegu_link_node_geocode_cache.json
  docs/data/extracted/its_nodelink/daegu_link_centroids_tmap_latest.csv
  docs/data/extracted/its_nodelink/meta_tmap_centroids.json

Not ETA. Not a collection loop. Does not fill D1 eta_minutes.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd
from dotenv import load_dotenv

_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))
from _bootstrap import ensure_paths

REPO = ensure_paths()
OUT = REPO / "docs/data/extracted/its_nodelink"
CACHE = OUT / "daegu_link_node_geocode_cache.json"
CENTROIDS = OUT / "daegu_link_centroids_tmap_latest.csv"
META = OUT / "meta_tmap_centroids.json"
TMAP_URL = "https://apis.openapi.sk.com/tmap/pois"
SLEEP_S = 0.25
DAEGU_BBOX = (35.70, 36.05, 128.35, 128.80)  # lat_min, lat_max, lng_min, lng_max


def _latest_linkspeed() -> Path:
    loop3 = REPO / "docs/data/loops/loop3"
    files = sorted(loop3.glob("*/daegu_traffic_linkspeed_*.csv"))
    files = [p for p in files if "latest" not in p.name]
    if not files:
        raise FileNotFoundError("no loop3 linkspeed csv")
    return files[-1]


def _tmap_poi(keyword: str, appkey: str) -> dict | None:
    params = {
        "version": "1",
        "searchKeyword": keyword,
        "page": "1",
        "searchType": "all",
        "count": "5",
        "resCoordType": "WGS84GEO",
        "reqCoordType": "WGS84GEO",
        "multiPoint": "N",
    }
    req = Request(
        f"{TMAP_URL}?{urlencode(params)}",
        headers={"accept": "application/json", "appkey": appkey},
    )
    last_err: Exception | None = None
    for attempt in range(3):
        try:
            with urlopen(req, timeout=20) as resp:
                raw = resp.read().decode("utf-8")
            if not raw.strip():
                raise ValueError("empty body")
            data = json.loads(raw)
            break
        except Exception as e:
            last_err = e
            time.sleep(0.8 * (attempt + 1))
            data = None
    if data is None:
        raise last_err or RuntimeError("tmap failed")
    pois = data.get("searchPoiInfo", {}).get("pois", {}).get("poi", []) or []
    lat_min, lat_max, lng_min, lng_max = DAEGU_BBOX
    for poi in pois:
        try:
            lat = float(poi.get("frontLat"))
            lng = float(poi.get("frontLon"))
        except (TypeError, ValueError):
            continue
        if lat_min <= lat <= lat_max and lng_min <= lng <= lng_max:
            return {
                "lat": lat,
                "lng": lng,
                "match_name": str(poi.get("name") or ""),
                "query": keyword,
            }
    return None


def main() -> int:
    load_dotenv(REPO / ".env")
    appkey = (os.getenv("TMAP_APP_KEY") or "").strip()
    if not appkey or "MOCK" in appkey.upper():
        print("FAIL: TMAP_APP_KEY missing")
        return 1

    link_path = _latest_linkspeed()
    links = pd.read_csv(link_path, dtype=str)
    for c in ("startNodeNm", "endNodeNm", "linkId", "roadName"):
        if c not in links.columns:
            print(f"FAIL: missing column {c}")
            return 1

    nodes = sorted(
        {
            str(x).strip()
            for x in pd.concat([links["startNodeNm"], links["endNodeNm"]], ignore_index=True)
            if str(x).strip() and str(x).strip().lower() != "nan"
        }
    )
    OUT.mkdir(parents=True, exist_ok=True)
    cache: dict = {}
    if CACHE.is_file():
        cache = json.loads(CACHE.read_text(encoding="utf-8"))

    ok = 0
    fail = 0
    for i, node in enumerate(nodes, 1):
        cached = cache.get(node) or {}
        if cached.get("lat") is not None:
            ok += 1
            continue
        # retry previous misses
        hit = None
        for q in (f"대구 {node}", f"대구광역시 {node}", node):
            try:
                hit = _tmap_poi(q, appkey)
            except Exception as e:
                print(f"  ERR {node}: {e}")
                hit = None
            time.sleep(SLEEP_S)
            if hit:
                break
        if hit:
            cache[node] = hit
            ok += 1
            print(f"[{i}/{len(nodes)}] OK {node} -> {hit['match_name']} ({hit['lat']:.5f},{hit['lng']:.5f})")
        else:
            cache[node] = {"lat": None, "lng": None, "match_name": "", "query": f"대구 {node}"}
            fail += 1
            print(f"[{i}/{len(nodes)}] MISS {node}")
        if i % 20 == 0:
            CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")

    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")

    rows = []
    for _, r in links.drop_duplicates("linkId").iterrows():
        a = cache.get(str(r["startNodeNm"]).strip()) or {}
        b = cache.get(str(r["endNodeNm"]).strip()) or {}
        if a.get("lat") is None or b.get("lat") is None:
            rows.append(
                {
                    "linkId": r["linkId"],
                    "roadName": r.get("roadName"),
                    "startNodeNm": r["startNodeNm"],
                    "endNodeNm": r["endNodeNm"],
                    "lat": None,
                    "lng": None,
                    "geom_source": "tmap_node_midpoint",
                    "geom_ok": False,
                }
            )
            continue
        lat = (float(a["lat"]) + float(b["lat"])) / 2.0
        lng = (float(a["lng"]) + float(b["lng"])) / 2.0
        rows.append(
            {
                "linkId": r["linkId"],
                "roadName": r.get("roadName"),
                "startNodeNm": r["startNodeNm"],
                "endNodeNm": r["endNodeNm"],
                "lat": round(lat, 7),
                "lng": round(lng, 7),
                "geom_source": "tmap_node_midpoint",
                "geom_ok": True,
            }
        )

    out = pd.DataFrame(rows)
    out.to_csv(CENTROIDS, index=False, encoding="utf-8-sig")
    meta = {
        "method": "TMAP POI geocode of start/end node names → midpoint",
        "note": "Interim until official MOCT_LINK SHP is placed under extracted/its_nodelink/",
        "linkspeed_source": str(link_path.relative_to(REPO)).replace("\\", "/"),
        "n_unique_nodes": len(nodes),
        "n_nodes_geocoded": ok,
        "n_nodes_miss": fail,
        "n_links": int(len(out)),
        "n_links_geom_ok": int(out["geom_ok"].sum()),
        "outputs": {
            "cache": str(CACHE.relative_to(REPO)).replace("\\", "/"),
            "centroids": str(CENTROIDS.relative_to(REPO)).replace("\\", "/"),
        },
    }
    META.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    return 0 if out["geom_ok"].any() else 2


if __name__ == "__main__":
    raise SystemExit(main())
