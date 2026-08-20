"""Geocode City Tour POIs using TMAP POI API.

Reads poi_city_tour_no_coords.csv and fetches WGS84 coords via TMAP.
Outputs poi_city_tour_geocoded.csv for spatial join.
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen

from dotenv import load_dotenv

import sys
from pathlib import Path
_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))
from _bootstrap import ensure_paths

REPO = ensure_paths()

SANDBOX = REPO / "apps/data-pipeline/evaluation/personal/experiments/SANDBOX_20260716_preprocess_pipeline"
PROC = SANDBOX / "data/processed"

IN_CSV = PROC / "poi_city_tour_no_coords.csv"
OUT_CSV = PROC / "poi_city_tour_geocoded.csv"
CACHE_JSON = PROC / "geocode_tmap_cache.json"

TMAP_URL = "https://apis.openapi.sk.com/tmap/pois"


def _load_key() -> str:
    load_dotenv(REPO / ".env")
    key = os.environ.get("TMAP_APP_KEY", "").strip()
    if not key:
        raise RuntimeError("TMAP_APP_KEY missing in .env")
    return key


def _search_tmap(keyword: str, appkey: str) -> tuple[str, str, str]:
    """Returns (lat, lng, match_name) or None."""
    if not keyword.strip():
        return "", "", ""
        
    params = {
        "version": "1",
        "searchKeyword": keyword,
        "page": "1",
        "searchType": "all",
        "count": "1",
        "resCoordType": "WGS84GEO",
        "reqCoordType": "WGS84GEO",
        "multiPoint": "N",
    }
    url = f"{TMAP_URL}?{urlencode(params)}"
    req = Request(url, headers={"accept": "application/json", "appkey": appkey})
    
    try:
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            
        pois = data.get("searchPoiInfo", {}).get("pois", {}).get("poi", [])
        if not pois:
            return "", "", ""
            
        # Get first result
        poi = pois[0]
        lat = str(poi.get("frontLat", ""))
        lng = str(poi.get("frontLon", ""))
        name = str(poi.get("name", ""))
        return lat, lng, name
    except Exception as e:
        print(f"  [API Error] {e}")
        return "", "", ""


def main() -> int:
    appkey = _load_key()
    
    if not IN_CSV.exists():
        print(f"Input file not found: {IN_CSV}")
        return 1

    # Load cache
    cache = {}
    if CACHE_JSON.exists():
        with open(CACHE_JSON, "r", encoding="utf-8") as f:
            cache = json.load(f)

    # Read input CSV
    rows = []
    with open(IN_CSV, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        if "lat" not in fieldnames: fieldnames.append("lat")
        if "lng" not in fieldnames: fieldnames.append("lng")
        if "tmap_match" not in fieldnames: fieldnames.append("tmap_match")
        
        for r in reader:
            rows.append(r)

    print(f"Loaded {len(rows)} POIs from {IN_CSV.name}")
    
    success = 0
    new_requests = 0

    # Geocode
    for r in rows:
        poi_id = r.get("poi_id", "")
        name = r.get("name", "")
        address = r.get("address", "")
        
        # Already has coords?
        if r.get("lat") and r.get("lng") and str(r.get("lat")).strip():
            success += 1
            continue
            
        # Check cache
        if poi_id in cache:
            lat, lng, match_nm = cache[poi_id]
        else:
            search_term = name
            if not search_term:
                search_term = address
                
            print(f"Searching TMAP: {search_term} ... ", end="", flush=True)
            lat, lng, match_nm = _search_tmap(search_term, appkey)
            time.sleep(0.1) # Be nice to API
            
            if not lat and address:
                # Fallback to address
                print(f"Fallback to address: {address} ... ", end="", flush=True)
                lat, lng, match_nm = _search_tmap(address, appkey)
                time.sleep(0.1)
                
            if lat:
                print(f"OK ({lat}, {lng}) - {match_nm}", flush=True)
            else:
                print("FAIL", flush=True)
                
            cache[poi_id] = (lat, lng, match_nm)
            new_requests += 1

            # Save cache every 20 requests
            if new_requests % 20 == 0:
                with open(CACHE_JSON, "w", encoding="utf-8") as f:
                    json.dump(cache, f, ensure_ascii=False, indent=2)

        # Update row
        if lat and lng:
            r["lat"] = lat
            r["lng"] = lng
            r["tmap_match"] = match_nm
            r["has_coords"] = "True"
            r["needs_geocoding"] = "False"
            success += 1
            
    # Final cache save
    with open(CACHE_JSON, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

    # Save output
    with open(OUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
        
    print(f"\nGeocoding complete! {success}/{len(rows)} successful.")
    print(f"Saved to: {OUT_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
