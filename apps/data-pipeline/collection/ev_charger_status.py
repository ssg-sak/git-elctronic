"""한국환경공단 EvCharger getChargerStatus 수집기 (실시간 상태, 2~5분 간격).

statUpdDt(상태 갱신 시각)와 fetchedAt(조회 시각)을 반드시 분리 저장한다.
getChargerInfo와 일 호출 한도(1,000건/일)를 공유하므로 호출 전 잔여 여유를 확인한다.

단독 실행: python ev_charger_status.py
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Optional

import config
import db
from http_client import ApiCallError, archive_raw, request_with_retry
from logging_conf import get_logger

logger = get_logger(__name__)

BASE_URL = "https://apis.data.go.kr/B552584/EvCharger/getChargerStatus"
API_NAME = "ev_charger_status"
PAGE_SIZE = 100
DAILY_LIMIT_SAFETY_MARGIN = 20
# EvCharger는 응답이 느려 502/504·타임아웃이 잦다 (scripts/api-tests에서 검증된 값)
REQUEST_TIMEOUT_SECONDS = 90


def _text(item: ET.Element, tag: str) -> Optional[str]:
    el = item.find(tag)
    return el.text.strip() if el is not None and el.text else None


def _parse(xml_text: str) -> tuple[str, list[ET.Element]]:
    root = ET.fromstring(xml_text)
    result_code = root.findtext("header/resultCode", default="")
    items = root.findall("body/items/item")
    return result_code, items


def _upsert_status(items: list[ET.Element], fetched_at: str) -> int:
    rows = []
    for item in items:
        stat_id = _text(item, "statId")
        chger_id = _text(item, "chgerId")
        if not stat_id or not chger_id:
            continue
        rows.append(
            (
                stat_id,
                chger_id,
                _text(item, "stat"),
                _text(item, "statNm"),
                _text(item, "statUpdDt"),
                fetched_at,
            )
        )
    if not rows:
        return 0
    with db.get_connection() as conn:
        conn.executemany(
            """
            INSERT INTO chargers (stat_id, chger_id, stat, stat_nm, stat_updated_at, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(stat_id, chger_id) DO UPDATE SET
                stat=excluded.stat, stat_nm=excluded.stat_nm,
                stat_updated_at=excluded.stat_updated_at, fetched_at=excluded.fetched_at
            """,
            rows,
        )
    return len(rows)


def collect(zcode: str = config.ZCODE, period_minutes: int = config.STATUS_PERIOD_MINUTES) -> int:
    already_called = db.ev_combined_calls_today()
    if already_called >= config.EV_API_DAILY_LIMIT - DAILY_LIMIT_SAFETY_MARGIN:
        logger.warning(
            "EvCharger 일 호출 한도 근접(%s/%s) — 이번 회차 상태 수집 건너뜀",
            already_called,
            config.EV_API_DAILY_LIMIT,
        )
        return 0

    page_no = 1
    total_updated = 0
    while True:
        try:
            resp = request_with_retry(
                "GET",
                BASE_URL,
                params={
                    "serviceKey": config.DATA_GO_KR_KEY,
                    "pageNo": page_no,
                    "numOfRows": PAGE_SIZE,
                    "zcode": zcode,
                    "period": period_minutes,
                },
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except ApiCallError as exc:
            db.log_api_call(API_NAME, None, False, note=str(exc))
            logger.error(
                "getChargerStatus page %s에서 중단 (지금까지 %s건은 갱신됨): %s", page_no, total_updated, exc
            )
            raise
        archive_raw(API_NAME, resp.text, "xml")
        result_code, items = _parse(resp.text)
        if result_code != "00":
            db.log_api_call(API_NAME, resp.status_code, False, note=f"resultCode={result_code}")
            raise RuntimeError(f"getChargerStatus 실패: resultCode={result_code}")

        fetched_at = db.now_iso()
        updated = _upsert_status(items, fetched_at)
        db.log_api_call(API_NAME, resp.status_code, True, item_count=len(items))
        total_updated += updated
        logger.info("getChargerStatus page %s: %s건 갱신", page_no, updated)

        if len(items) < PAGE_SIZE:
            break
        page_no += 1

    logger.info(
        "getChargerStatus 총 %s건 갱신 완료 (zcode=%s, period=%s분)", total_updated, zcode, period_minutes
    )
    return total_updated


def main() -> None:
    db.init_db()
    collect()


if __name__ == "__main__":
    main()
