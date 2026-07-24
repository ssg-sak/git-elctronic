"""Extract TourAPI (KorService2) attractions near Daegu center.

Outputs UTF-8 CSV under docs/data/extracted/.
Uses DATA_GO_KR_KEY from repo-root .env.
"""
from __future__ import annotations

import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

import sys
from pathlib import Path
_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))
from _bootstrap import ensure_paths

REPO = ensure_paths()
from loop_paths import EXTRACTED_TOUR

OUT_DIR = EXTRACTED_TOUR
KST = ZoneInfo("Asia/Seoul")

BASE_URL = "https://apis.data.go.kr/B551011/KorService2/locationBasedList2"
DAEGU_X = 128.6014
DAEGU_Y = 35.8714
RADIUS = 5000
CONTENT_TYPE_ID = 12

FIELDS = [
    "contentid",
    "title",
    "addr1",
    "addr2",
    "mapx",
    "mapy",
    "dist",
    "cat1",
    "cat2",
    "cat3",
    "tel",
    "firstimage",
    "fetchedAt",
]


def _fetch_page(service_key: str, page: int) -> dict[str, Any]:
    params = {
        "serviceKey": service_key,
        "MobileOS": "ETC",
        "MobileApp": "EVSafeCharge",
        "_type": "json",
        "mapX": str(DAEGU_X),
        "mapY": str(DAEGU_Y),
        "radius": str(RADIUS),
        "numOfRows": "100",
        "pageNo": str(page),
        "contentTypeId": str(CONTENT_TYPE_ID),
    }
    url = f"{BASE_URL}?{urlencode(params)}"
    req = Request(url, headers={"Accept": "application/json; charset=utf-8"})
    with urlopen(req, timeout=60) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw)


def extract(service_key: str) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(KST).strftime("%Y%m%d_%H%M%S")
    out_path = OUT_DIR / f"daegu_tour_attractions_{ts}.csv"
    fetched_at = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")

    page = 1
    total: int | None = None
    acc = 0

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, quoting=csv.QUOTE_ALL)
        writer.writeheader()

        while True:
            data = _fetch_page(service_key, page)
            header = data.get("response", {}).get("header", {})
            if header.get("resultCode") != "0000":
                raise RuntimeError(
                    f"TourAPI error: {header.get('resultCode')} {header.get('resultMsg')}"
                )

            body = data.get("response", {}).get("body", {})
            items = body.get("items", {}).get("item", [])
            if isinstance(items, dict):
                items = [items]
            if not items:
                break

            if total is None:
                total = int(body.get("totalCount", 0) or 0)

            for item in items:
                writer.writerow(
                    {
                        "contentid": item.get("contentid", ""),
                        "title": item.get("title", ""),
                        "addr1": item.get("addr1", ""),
                        "addr2": item.get("addr2", ""),
                        "mapx": item.get("mapx", ""),
                        "mapy": item.get("mapy", ""),
                        "dist": item.get("dist", ""),
                        "cat1": item.get("cat1", ""),
                        "cat2": item.get("cat2", ""),
                        "cat3": item.get("cat3", ""),
                        "tel": item.get("tel", ""),
                        "firstimage": item.get("firstimage", ""),
                        "fetchedAt": fetched_at,
                    }
                )
                acc += 1

            print(f"  page {page}: {len(items)} (acc {acc}/{total or '?'})")
            if total and acc >= total:
                break
            if len(items) < 100:
                break
            page += 1
            if page > 30:
                break

    print(f"SAVED {acc} rows -> {out_path}")
    return out_path


def main() -> int:
    load_dotenv(REPO / ".env")
    key = os.getenv("DATA_GO_KR_KEY", "").strip()
    if not key:
        print("DATA_GO_KR_KEY missing in .env", file=sys.stderr)
        return 1
    extract(key)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
