"""Sandbox status snapshot collector.

Hard rules (EXP-012):
1. Never write to docs/data/extracted/
2. Only write under docs/data/loops/loop1/
3. Respect EvCharger daily call limit with safety margin
"""
from __future__ import annotations

import csv
import json
import os
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[7]  # -> git-elctronic
import sys

_DATA_PIPELINE = REPO_ROOT / "apps" / "data-pipeline"
if str(_DATA_PIPELINE) not in sys.path:
    sys.path.insert(0, str(_DATA_PIPELINE))

from loop_paths import EXTRACTED_DIR, LOOP1_DIR, LOOP1_INDEX, LOOP1_LOGS, LOOP1_SNAPSHOTS

SNAPSHOT_DIR = LOOP1_SNAPSHOTS
LOG_DIR = LOOP1_LOGS
INDEX_CSV = LOOP1_INDEX
QUOTA_JSON = LOG_DIR / "daily_quota.json"
CALL_LOG = LOG_DIR / "call_log.jsonl"

BASE_URL = "https://apis.data.go.kr/B552584/EvCharger/getChargerStatus"
ZCODE = "27"
PAGE_SIZE = 100
EV_API_DAILY_LIMIT = 1000
SAFETY_MARGIN = 50
REQUEST_TIMEOUT = 90
MAX_RETRIES = 2
KST = ZoneInfo("Asia/Seoul")

CSV_FIELDS = [
    "statId",
    "chgerId",
    "stat",
    "statNm",
    "statUpdDt",
    "fetchedAt",
    "snapshotId",
    "pageNo",
]


def _ensure_dirs() -> None:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    assert not str(SNAPSHOT_DIR).startswith(str(EXTRACTED_DIR)), "REFUSING to write under extracted/"


def _now_kst() -> datetime:
    return datetime.now(tz=KST)


def _load_key() -> str:
    load_dotenv(REPO_ROOT / ".env")
    key = os.environ.get("DATA_GO_KR_KEY", "").strip()
    if not key:
        raise RuntimeError("DATA_GO_KR_KEY missing in environment / .env")
    return key


def _today_key() -> str:
    return _now_kst().strftime("%Y-%m-%d")


def _read_quota() -> dict[str, Any]:
    if not QUOTA_JSON.exists():
        return {"date": _today_key(), "calls": 0}
    data = json.loads(QUOTA_JSON.read_text(encoding="utf-8"))
    if data.get("date") != _today_key():
        return {"date": _today_key(), "calls": 0}
    return data


def _write_quota(calls: int) -> None:
    QUOTA_JSON.write_text(
        json.dumps({"date": _today_key(), "calls": calls}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _append_call_log(entry: dict[str, Any]) -> None:
    with CALL_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _can_call(needed_pages_estimate: int = 1) -> tuple[bool, int]:
    quota = _read_quota()
    calls = int(quota.get("calls", 0))
    remaining = EV_API_DAILY_LIMIT - SAFETY_MARGIN - calls
    return remaining >= needed_pages_estimate, calls


def _bump_calls(n: int = 1) -> int:
    quota = _read_quota()
    calls = int(quota.get("calls", 0)) + n
    _write_quota(calls)
    return calls


def _text(item: ET.Element, tag: str) -> str | None:
    el = item.find(tag)
    if el is None or el.text is None:
        return None
    value = el.text.strip()
    return value or None


def _parse(xml_text: str) -> tuple[str, list[ET.Element]]:
    root = ET.fromstring(xml_text)
    result_code = root.findtext("header/resultCode", default="") or ""
    items = root.findall("body/items/item")
    return result_code, items


def _request_page(service_key: str, page_no: int, period_minutes: int) -> requests.Response:
    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = requests.get(
                BASE_URL,
                params={
                    "serviceKey": service_key,
                    "pageNo": page_no,
                    "numOfRows": PAGE_SIZE,
                    "zcode": ZCODE,
                    "period": period_minutes,
                },
                timeout=REQUEST_TIMEOUT,
            )
            if resp.status_code in {502, 503, 504} and attempt < MAX_RETRIES:
                time.sleep(3 * (attempt + 1))
                continue
            resp.raise_for_status()
            return resp
        except Exception as exc:  # noqa: BLE001 - log and retry
            last_exc = exc
            if attempt < MAX_RETRIES:
                time.sleep(3 * (attempt + 1))
                continue
            raise
    raise RuntimeError(f"request failed: {last_exc}")


def collect_snapshot(*, period_minutes: int = 10) -> dict[str, Any]:
    """Fetch getChargerStatus pages and write a timestamped CSV under SANDBOX only."""
    _ensure_dirs()
    if EXTRACTED_DIR.exists():
        # Soft guard: never open extracted for write
        pass

    ok, calls_so_far = _can_call(1)
    started = _now_kst()
    snapshot_id = started.strftime("%Y%m%d_%H%M%S")
    if not ok:
        result = {
            "ok": False,
            "skipped": True,
            "reason": "daily_limit_margin",
            "calls_so_far": calls_so_far,
            "limit": EV_API_DAILY_LIMIT,
            "safety_margin": SAFETY_MARGIN,
            "snapshot_id": snapshot_id,
        }
        _append_call_log({**result, "ts": started.isoformat()})
        return result

    service_key = _load_key()
    fetched_at = started.strftime("%Y-%m-%d %H:%M:%S")
    rows: list[dict[str, str | None]] = []
    page_no = 1
    api_calls = 0

    while True:
        still_ok, _ = _can_call(1)
        if not still_ok:
            break
        resp = _request_page(service_key, page_no, period_minutes)
        api_calls += 1
        _bump_calls(1)
        result_code, items = _parse(resp.text)
        if result_code != "00":
            _append_call_log(
                {
                    "ok": False,
                    "ts": started.isoformat(),
                    "snapshot_id": snapshot_id,
                    "resultCode": result_code,
                    "pageNo": page_no,
                    "status_code": resp.status_code,
                }
            )
            raise RuntimeError(f"getChargerStatus failed: resultCode={result_code}")

        for item in items:
            stat_id = _text(item, "statId")
            chger_id = _text(item, "chgerId")
            if not stat_id or not chger_id:
                continue
            rows.append(
                {
                    "statId": stat_id,
                    "chgerId": chger_id,
                    "stat": _text(item, "stat"),
                    "statNm": _text(item, "statNm"),
                    "statUpdDt": _text(item, "statUpdDt"),
                    "fetchedAt": fetched_at,
                    "snapshotId": snapshot_id,
                    "pageNo": str(page_no),
                }
            )

        if len(items) < PAGE_SIZE:
            break
        page_no += 1

    out_path = SNAPSHOT_DIR / f"daegu_charger_status_{snapshot_id}.csv"
    # Absolute path must stay inside sandbox
    if EXTRACTED_DIR.resolve() in out_path.resolve().parents or out_path.resolve().parent == EXTRACTED_DIR.resolve():
        raise RuntimeError("refusing to write snapshot into docs/data/extracted/")

    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    index_exists = INDEX_CSV.exists()
    with INDEX_CSV.open("a", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["snapshotId", "path", "rows", "api_calls", "period_minutes", "fetchedAt", "ok"],
        )
        if not index_exists:
            writer.writeheader()
        writer.writerow(
            {
                "snapshotId": snapshot_id,
                "path": str(out_path.relative_to(LOOP1_DIR)).replace("\\", "/"),
                "rows": len(rows),
                "api_calls": api_calls,
                "period_minutes": period_minutes,
                "fetchedAt": fetched_at,
                "ok": True,
            }
        )

    result = {
        "ok": True,
        "skipped": False,
        "snapshot_id": snapshot_id,
        "path": str(out_path),
        "rows": len(rows),
        "api_calls": api_calls,
        "calls_today": _read_quota()["calls"],
        "period_minutes": period_minutes,
        "zcode": ZCODE,
    }
    _append_call_log({**result, "ts": started.isoformat()})
    return result
