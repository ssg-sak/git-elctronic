"""Extract Daegu ITS traffic (linkspeed + dgincident) via data.go.kr.

Outputs under docs/data/loops/loop3/ (live loop track).
Uses DATA_GO_KR_KEY from repo-root .env.
Attribution: 대구광역시 교통정보 (ATMS) · 공공데이터포털.
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
from loop_paths import loop3_day_dir, loop3_dir, ymd_from_filename

OUT_DIR = loop3_dir()
KST = ZoneInfo("Asia/Seoul")

LINKSPEED_URL = "https://apis.data.go.kr/6270000/service/rest1/linkspeed"
INCIDENT_URL = "https://apis.data.go.kr/6270000/service/rest/dgincident"

CONG_NM = {"01": "원활", "02": "지체", "03": "정체"}

LINK_FIELDS = [
    "linkId",
    "roadName",
    "sectionNm",
    "startNodeNm",
    "endNodeNm",
    "distanceM",
    "speedKph",
    "travelTimeSec",
    "congGrade",
    "congGradeNm",
    "sectionInfoCd",
    "dsrcLinkSn",
    "atmsTm",
    "isMock",
    "traffic_source",
    "fetchedAt",
]

INCIDENT_FIELDS = [
    "incidentId",
    "location",
    "incidentTitle",
    "linkId",
    "coordX",
    "coordY",
    "troubleGrade",
    "incidentCode",
    "incidentSubCode",
    "startDate",
    "endDate",
    "reportDate",
    "logDate",
    "isMock",
    "traffic_source",
    "fetchedAt",
]


def _load_key() -> str:
    load_dotenv(REPO / ".env")
    key = os.environ.get("DATA_GO_KR_KEY", "").strip()
    if not key:
        raise RuntimeError("DATA_GO_KR_KEY missing in .env")
    return key


def _fetch_json(url: str, key: str, *, num_of_rows: int = 9999) -> dict[str, Any]:
    params = urlencode(
        {"serviceKey": key, "pageNo": "1", "numOfRows": str(num_of_rows)},
        safe="%",
    )
    req = Request(f"{url}?{params}", headers={"User-Agent": "EV-SafeCharge-data-pipeline/1.0"})
    with urlopen(req, timeout=120) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    header = payload.get("header") or payload.get("response", {}).get("header", {})
    code = str(header.get("resultCode", ""))
    if code not in ("00", "0", ""):
        msg = header.get("resultMsg", "")
        raise RuntimeError(f"API resultCode={code} {msg}")
    return payload


def _items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    body = payload.get("body") or payload.get("response", {}).get("body", {})
    raw = body.get("items", {}).get("item", [])
    if not raw:
        return []
    if isinstance(raw, dict):
        return [raw]
    return list(raw)


def _normalize_link(item: dict[str, Any], fetched_at: str) -> dict[str, str]:
    section_cd = str(item.get("SECTION_INFO_CD", "") or "").zfill(2)
    cong = section_cd.lstrip("0") or section_cd
    return {
        "linkId": str(item.get("STD_LINK_ID", "") or ""),
        "roadName": str(item.get("ROAD_NM", "") or ""),
        "sectionNm": str(item.get("SECTION_NM", "") or ""),
        "startNodeNm": str(item.get("START_FAC_NM", "") or ""),
        "endNodeNm": str(item.get("END_FAC_NM", "") or ""),
        "distanceM": str(item.get("DIST", "") or ""),
        "speedKph": str(item.get("LINK_SPEED", "") or ""),
        "travelTimeSec": str(item.get("LINK_TIME", "") or ""),
        "congGrade": cong,
        "congGradeNm": CONG_NM.get(section_cd, ""),
        "sectionInfoCd": section_cd,
        "dsrcLinkSn": str(item.get("DSRC_LINK_SN", "") or ""),
        "atmsTm": str(item.get("ATMS_TM", "") or ""),
        "isMock": "false",
        "traffic_source": "daegu_live",
        "fetchedAt": fetched_at,
    }


def _normalize_incident(item: dict[str, Any], fetched_at: str) -> dict[str, str]:
    return {
        "incidentId": str(item.get("INCIDENTID", "") or ""),
        "location": str(item.get("LOCATION", "") or ""),
        "incidentTitle": str(item.get("INCIDENTTITLE", "") or ""),
        "linkId": str(item.get("LINKID", "") or ""),
        "coordX": str(item.get("COORDX", "") or ""),
        "coordY": str(item.get("COORDY", "") or ""),
        "troubleGrade": str(item.get("TROUBLEGRADE", "") or ""),
        "incidentCode": str(item.get("INCIDENTCODE", "") or ""),
        "incidentSubCode": str(item.get("INCIDENTSUBCODE", "") or ""),
        "startDate": str(item.get("STARTDATE", "") or ""),
        "endDate": str(item.get("ENDDATE", "") or ""),
        "reportDate": str(item.get("REPORTDATE", "") or ""),
        "logDate": str(item.get("LOGDATE", "") or ""),
        "isMock": "false",
        "traffic_source": "daegu_live",
        "fetchedAt": fetched_at,
    }


def _write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def extract(*, key: str | None = None) -> dict[str, Any]:
    api_key = key or _load_key()
    now = datetime.now(KST)
    stamp = now.strftime("%Y%m%d_%H%M%S")
    fetched_at = now.strftime("%Y-%m-%d %H:%M:%S")

    link_payload = _fetch_json(LINKSPEED_URL, api_key)
    link_items = _items(link_payload)
    link_rows = [_normalize_link(item, fetched_at) for item in link_items]

    inc_payload = _fetch_json(INCIDENT_URL, api_key)
    inc_items = _items(inc_payload)
    inc_rows = [_normalize_incident(item, fetched_at) for item in inc_items]

    ymd = stamp[:8]
    day_dir = loop3_day_dir(ymd)
    day_dir.mkdir(parents=True, exist_ok=True)
    link_path = day_dir / f"daegu_traffic_linkspeed_{stamp}.csv"
    inc_path = day_dir / f"daegu_traffic_incident_{stamp}.csv"
    _write_csv(link_path, LINK_FIELDS, link_rows)
    _write_csv(inc_path, INCIDENT_FIELDS, inc_rows)

    link_latest = OUT_DIR / "daegu_traffic_linkspeed_latest.csv"
    inc_latest = OUT_DIR / "daegu_traffic_incident_latest.csv"
    link_latest.write_bytes(link_path.read_bytes())
    inc_latest.write_bytes(inc_path.read_bytes())

    speeds = [float(r["speedKph"]) for r in link_rows if r.get("speedKph")]
    cong_counts = {k: sum(1 for r in link_rows if r.get("congGrade") == k) for k in ("1", "2", "3")}

    meta = {
        "source": "daegu_its",
        "attribution": "대구광역시 교통정보(ATMS) · 공공데이터포털",
        "fetched_at": now.isoformat(),
        "api_status": "ok",
        "linkspeed": {
            "rows": len(link_rows),
            "file": str(link_path.relative_to(REPO)).replace("\\", "/"),
            "latest": str(link_latest.relative_to(REPO)).replace("\\", "/"),
            "speed_kph_mean": round(sum(speeds) / len(speeds), 1) if speeds else None,
            "cong_grade_counts": cong_counts,
            "atms_tm_sample": link_rows[0]["atmsTm"] if link_rows else None,
            "note": "링크별 좌표 없음 — 충전소 조인은 링크맵·경로(TMAP) 후속",
        },
        "incident": {
            "rows": len(inc_rows),
            "file": str(inc_path.relative_to(REPO)).replace("\\", "/"),
            "latest": str(inc_latest.relative_to(REPO)).replace("\\", "/"),
        },
        "traffic_is_mock": False,
        "traffic_source": "daegu_live",
    }
    meta_path = OUT_DIR / f"daegu_traffic_meta_{stamp}.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT_DIR / "daegu_traffic_meta_latest.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return meta


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    meta = extract()
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
