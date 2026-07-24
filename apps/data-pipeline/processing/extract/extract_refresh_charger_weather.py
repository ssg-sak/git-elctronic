"""Refresh Daegu charger info extract into docs/data/extracted/.

Uses DATA_GO_KR_KEY from .env. Does not touch status loop snapshots.
날씨 추출은 2026-07-22 팀 합의로 중단·데이터 삭제.
"""
from __future__ import annotations

import csv
import json
import os
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path
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
from loop_paths import EXTRACTED_CHARGER_INFO

OUT = EXTRACTED_CHARGER_INFO
KST = ZoneInfo("Asia/Seoul")

INFO_URL = "https://apis.data.go.kr/B552584/EvCharger/getChargerInfo"
NCST_URL = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst"
FCST_URL = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtFcst"
VILAGE_URL = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst"


def _key() -> str:
    load_dotenv(REPO / ".env")
    key = os.environ.get("DATA_GO_KR_KEY", "").strip()
    if not key:
        raise RuntimeError("DATA_GO_KR_KEY missing")
    return key


def _get(url: str, params: dict, timeout: int = 120) -> bytes:
    q = urlencode(params, doseq=True, safe="%")
    # serviceKey already encoded if from portal; urllib encodes again — use quote via safe
    req = Request(f"{url}?{q}", headers={"User-Agent": "EV-SafeCharge-data-pipeline/1.0"})
    with urlopen(req, timeout=timeout) as resp:
        return resp.read()


def extract_charger_info(key: str, stamp: str) -> Path:
    page = 1
    rows: list[dict[str, str]] = []
    total = None
    while True:
        raw = _get(
            INFO_URL,
            {
                "serviceKey": key,
                "pageNo": str(page),
                "numOfRows": "999",
                "zcode": "27",
            },
            timeout=150,
        )
        root = ET.fromstring(raw)
        header = root.find(".//header")
        result = (header.findtext("resultCode") if header is not None else "") or ""
        if result not in ("00", "0", ""):
            msg = header.findtext("resultMsg") if header is not None else ""
            raise RuntimeError(f"getChargerInfo resultCode={result} {msg}")
        items = root.findall(".//item")
        if not items:
            break
        if total is None:
            t = root.findtext(".//body/totalCount")
            total = int(t) if t else None
        fetched = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
        for it in items:
            row = {c.tag: (c.text or "").strip() for c in it}
            row["fetchedAt"] = fetched
            rows.append(row)
        print(f"  charger_info page={page} items={len(items)} acc={len(rows)} total={total}")
        if total is not None and len(rows) >= total:
            break
        if len(items) < 999:
            break
        page += 1
        time.sleep(0.3)

    path = OUT / f"daegu_charger_info_{stamp}.csv"
    if not rows:
        raise RuntimeError("no charger info rows")
    fields = list(rows[0].keys())
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"SAVED charger_info {len(rows)} -> {path.relative_to(REPO)}")
    return path


def _weather_base() -> tuple[str, str]:
    # KMA often needs ~40-50 min lag for ncst base_time
    base = datetime.now(KST) - timedelta(minutes=50)
    return base.strftime("%Y%m%d"), base.strftime("%H") + "00"


def extract_weather_ncst(key: str, stamp: str) -> Path:
    base_date, base_time = _weather_base()
    raw = _get(
        NCST_URL,
        {
            "serviceKey": key,
            "pageNo": "1",
            "numOfRows": "20",
            "dataType": "JSON",
            "base_date": base_date,
            "base_time": base_time,
            "nx": "89",
            "ny": "90",
        },
    )
    data = json.loads(raw.decode("utf-8"))
    hdr = data["response"]["header"]
    if hdr.get("resultCode") != "00":
        raise RuntimeError(f"ncst {hdr}")
    fetched = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
    items = data["response"]["body"]["items"]["item"]
    if isinstance(items, dict):
        items = [items]
    rows = []
    for it in items:
        rows.append(
            {
                "baseDate": it.get("baseDate", ""),
                "baseTime": it.get("baseTime", ""),
                "category": it.get("category", ""),
                "obsrValue": it.get("obsrValue", ""),
                "nx": it.get("nx", ""),
                "ny": it.get("ny", ""),
                "fetchedAt": fetched,
            }
        )
    path = OUT / f"daegu_weather_ultra_ncst_{stamp}.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"SAVED weather_ncst {len(rows)} -> {path.relative_to(REPO)}")
    return path


def extract_weather_fcst(key: str, stamp: str) -> Path:
    base_date, base_time = _weather_base()
    raw = _get(
        FCST_URL,
        {
            "serviceKey": key,
            "pageNo": "1",
            "numOfRows": "100",
            "dataType": "JSON",
            "base_date": base_date,
            "base_time": base_time,
            "nx": "89",
            "ny": "90",
        },
    )
    data = json.loads(raw.decode("utf-8"))
    hdr = data["response"]["header"]
    if hdr.get("resultCode") != "00":
        raise RuntimeError(f"fcst {hdr}")
    fetched = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
    items = data["response"]["body"]["items"]["item"]
    if isinstance(items, dict):
        items = [items]
    rows = []
    for it in items:
        rows.append(
            {
                "baseDate": it.get("baseDate", ""),
                "baseTime": it.get("baseTime", ""),
                "fcstDate": it.get("fcstDate", ""),
                "fcstTime": it.get("fcstTime", ""),
                "category": it.get("category", ""),
                "fcstValue": it.get("fcstValue", ""),
                "nx": it.get("nx", ""),
                "ny": it.get("ny", ""),
                "fetchedAt": fetched,
            }
        )
    path = OUT / f"daegu_weather_ultra_fcst_{stamp}.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"SAVED weather_fcst {len(rows)} -> {path.relative_to(REPO)}")
    return path


def extract_weather_vilage(key: str, stamp: str) -> Path:
    # vilage: base_time typically 0200/0500/0800/1100/1400/1700/2000/2300
    now = datetime.now(KST) - timedelta(hours=1)
    slots = [2, 5, 8, 11, 14, 17, 20, 23]
    hour = now.hour
    bt = max([s for s in slots if s <= hour], default=23)
    if bt == 23 and hour < 2:
        base_date = (now - timedelta(days=1)).strftime("%Y%m%d")
    else:
        base_date = now.strftime("%Y%m%d")
    base_time = f"{bt:02d}00"
    raw = _get(
        VILAGE_URL,
        {
            "serviceKey": key,
            "pageNo": "1",
            "numOfRows": "1000",
            "dataType": "JSON",
            "base_date": base_date,
            "base_time": base_time,
            "nx": "89",
            "ny": "90",
        },
    )
    data = json.loads(raw.decode("utf-8"))
    hdr = data["response"]["header"]
    if hdr.get("resultCode") != "00":
        raise RuntimeError(f"vilage {hdr}")
    fetched = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
    items = data["response"]["body"]["items"]["item"]
    if isinstance(items, dict):
        items = [items]
    rows = []
    for it in items:
        rows.append(
            {
                "baseDate": it.get("baseDate", ""),
                "baseTime": it.get("baseTime", ""),
                "fcstDate": it.get("fcstDate", ""),
                "fcstTime": it.get("fcstTime", ""),
                "category": it.get("category", ""),
                "fcstValue": it.get("fcstValue", ""),
                "nx": it.get("nx", ""),
                "ny": it.get("ny", ""),
                "fetchedAt": fetched,
            }
        )
    path = OUT / f"daegu_weather_vilage_fcst_{stamp}.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"SAVED weather_vilage {len(rows)} -> {path.relative_to(REPO)}")
    return path


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    key = _key()
    stamp = datetime.now(KST).strftime("%Y%m%d_%H%M%S")
    print(f"=== extract charger info stamp={stamp} ===")
    extract_charger_info(key, stamp)
    print("DONE (weather extract disabled — team decision 2026-07-22)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
