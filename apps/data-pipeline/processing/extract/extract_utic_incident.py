"""Extract UTIC incident open data → Daegu CSV (DATA_PART / ALT_API).

Requires UTIC_API_KEY in repo-root .env. Does not commit secrets.
Attribution: 경찰청 도시교통정보센터(UTIC).
"""
from __future__ import annotations

import csv
import json
import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from urllib.request import urlopen, Request

from dotenv import load_dotenv

import sys
from pathlib import Path
_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))
from _bootstrap import ensure_paths

REPO = ensure_paths()
from loop_paths import loop2_dir, loop3_dir

OUT_DIR = loop2_dir()
KST = ZoneInfo("Asia/Seoul")

INCIDENT_URL = "http://www.utic.go.kr/guide/imsOpenData.do"

# Daegu bbox (WGS84) — secondary filter; primary = address contains "대구"
DAEGU_LNG_MIN, DAEGU_LNG_MAX = 128.35, 128.85
DAEGU_LAT_MIN, DAEGU_LAT_MAX = 35.70, 36.05

FIELDS = [
    "incidentId",
    "incidenteTypeCd",
    "incidenteSubTypeCd",
    "addressJibun",
    "addressJibunCd",
    "addressNew",
    "linkId",
    "locationDataX",
    "locationDataY",
    "locationTypeCd",
    "locationData",
    "incidenteTrafficCd",
    "incidenteGradeCd",
    "incidentTitle",
    "incTrafficCode",
    "incidentRegionCd",
    "startDate",
    "endDate",
    "lane",
    "roadName",
    "sourceCode",
    "controlType",
    "important",
    "updateDate",
]


def _load_key() -> str:
    load_dotenv(REPO / ".env")
    key = os.environ.get("UTIC_API_KEY", "").strip()
    if not key:
        raise RuntimeError("UTIC_API_KEY missing in .env")
    return key


def fetch_incident_xml(key: str, timeout: int = 60) -> str:
    url = f"{INCIDENT_URL}?key={key}"
    req = Request(url, headers={"User-Agent": "EV-SafeCharge-data-pipeline/1.0"})
    with urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def parse_records(xml_text: str) -> list[dict[str, str]]:
    text = (xml_text or "").strip()
    if not text.startswith("<"):
        preview = text[:200].replace("\n", " ")
        raise RuntimeError(f"UTIC response is not XML (preview={preview!r})")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        preview = text[:200].replace("\n", " ")
        raise RuntimeError(f"UTIC XML parse failed: {exc}; preview={preview!r}") from exc
    rows: list[dict[str, str]] = []
    for rec in root.findall("record"):
        row = {f: (rec.findtext(f) or "").strip() for f in FIELDS}
        rows.append(row)
    return rows


def is_daegu(row: dict[str, str]) -> bool:
    addr = f"{row.get('addressJibun', '')} {row.get('addressNew', '')}"
    if "대구" in addr and "해운대구" not in addr:
        return True
    try:
        lng = float(row.get("locationDataX") or "nan")
        lat = float(row.get("locationDataY") or "nan")
    except ValueError:
        return False
    if not (DAEGU_LNG_MIN <= lng <= DAEGU_LNG_MAX and DAEGU_LAT_MIN <= lat <= DAEGU_LAT_MAX):
        return False
    # bbox hit without 대구 in address → keep only if not clearly other city
    if any(x in addr for x in ("부산", "울산", "경주", "구미", "포항", "창원")):
        return False
    return "대구" in addr or addr.strip() == ""


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS + ["traffic_source", "fetchedAt"])
        w.writeheader()
        for r in rows:
            out = dict(r)
            out["traffic_source"] = "utic"
            out["fetchedAt"] = out.get("fetchedAt", "")
            w.writerow({k: out.get(k, "") for k in w.fieldnames})


def main() -> int:
    key = _load_key()
    stamp = datetime.now(KST).strftime("%Y%m%d_%H%M%S")
    fetched_at = datetime.now(KST).isoformat()

    xml_text = fetch_incident_xml(key)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    # Do NOT persist national XML / all-Korea CSV (Daegu-only policy).

    all_rows = parse_records(xml_text)
    for r in all_rows:
        r["fetchedAt"] = fetched_at

    daegu_addr = [
        r
        for r in all_rows
        if "대구" in f"{r.get('addressJibun', '')} {r.get('addressNew', '')}"
        and "해운대구" not in f"{r.get('addressJibun', '')} {r.get('addressNew', '')}"
    ]

    daegu_csv = OUT_DIR / f"daegu_traffic_incident_utic_{stamp}.csv"
    latest_csv = OUT_DIR / "daegu_traffic_incident_utic_latest.csv"

    write_csv(daegu_csv, daegu_addr)
    write_csv(latest_csv, daegu_addr)

    meta = {
        "source": "UTIC",
        "attribution": "경찰청 도시교통정보센터(UTIC)",
        "fetched_at": fetched_at,
        "endpoint": INCIDENT_URL,
        "national_records": len(all_rows),
        "daegu_records": len(daegu_addr),
        "daegu_filter": 'address contains "대구" and not "해운대구"',
        "files": {
            "daegu_csv": str(daegu_csv.relative_to(REPO)).replace("\\", "/"),
            "daegu_latest": str(latest_csv.relative_to(REPO)).replace("\\", "/"),
        },
        "persist_policy": "loops/loop2 keeps Daegu CSV only; national XML/CSV not saved",
        "traffic_is_mock": False,
        "traffic_source": "utic",
        "note": "join via join_utic_incident.py → D1 traffic_source=utic",
    }
    meta_path = OUT_DIR / f"utic_incident_meta_{stamp}.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT_DIR / "utic_incident_meta_latest.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(json.dumps(meta, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
