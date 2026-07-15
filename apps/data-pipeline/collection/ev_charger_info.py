"""한국환경공단 EvCharger getChargerInfo 수집기 (충전소·충전기 정적 정보, 1일 1회).

단독 실행: python ev_charger_info.py
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Optional

import config
import db
from http_client import ApiCallError, archive_raw, request_with_retry
from logging_conf import get_logger

logger = get_logger(__name__)

BASE_URL = "https://apis.data.go.kr/B552584/EvCharger/getChargerInfo"
API_NAME = "ev_charger_info"
PAGE_SIZE = 100
# EvCharger는 응답이 느려 502/504·타임아웃이 잦다 (scripts/api-tests에서 검증된 값)
REQUEST_TIMEOUT_SECONDS = 90


def _text(item: ET.Element, tag: str) -> Optional[str]:
    el = item.find(tag)
    return el.text.strip() if el is not None and el.text else None


def _float_or_none(value: Optional[str]) -> Optional[float]:
    try:
        return float(value) if value else None
    except ValueError:
        return None


def _parse(xml_text: str) -> tuple[str, list[ET.Element]]:
    root = ET.fromstring(xml_text)
    result_code = root.findtext("header/resultCode", default="")
    items = root.findall("body/items/item")
    return result_code, items


def _upsert(items: list[ET.Element], fetched_at: str) -> None:
    stations: dict[str, tuple] = {}
    chargers = []
    for item in items:
        stat_id = _text(item, "statId")
        if not stat_id:
            continue
        stations[stat_id] = (
            stat_id,
            _text(item, "statNm"),
            _text(item, "addr"),
            _float_or_none(_text(item, "lat")),
            _float_or_none(_text(item, "lng")),
            _text(item, "busiNm"),
            _text(item, "busiCall"),
            _text(item, "useTime"),
            _text(item, "parkingFree"),
            _text(item, "delYn"),
            fetched_at,
        )
        chger_id = _text(item, "chgerId")
        if chger_id:
            chargers.append(
                (
                    stat_id,
                    chger_id,
                    _text(item, "chgerType"),
                    _text(item, "output"),
                    _text(item, "method"),
                    _text(item, "stat"),
                    _text(item, "statNm"),
                    _text(item, "statUpdDt"),
                    fetched_at,
                )
            )

    with db.get_connection() as conn:
        conn.executemany(
            """
            INSERT INTO charging_stations
                (stat_id, stat_nm, addr, lat, lng, busi_nm, busi_call, use_time, parking_free, del_yn, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(stat_id) DO UPDATE SET
                stat_nm=excluded.stat_nm, addr=excluded.addr, lat=excluded.lat, lng=excluded.lng,
                busi_nm=excluded.busi_nm, busi_call=excluded.busi_call, use_time=excluded.use_time,
                parking_free=excluded.parking_free, del_yn=excluded.del_yn, fetched_at=excluded.fetched_at
            """,
            list(stations.values()),
        )
        conn.executemany(
            """
            INSERT INTO chargers
                (stat_id, chger_id, chger_type, output, method, stat, stat_nm, stat_updated_at, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(stat_id, chger_id) DO UPDATE SET
                chger_type=excluded.chger_type, output=excluded.output, method=excluded.method,
                stat=excluded.stat, stat_nm=excluded.stat_nm, stat_updated_at=excluded.stat_updated_at,
                fetched_at=excluded.fetched_at
            """,
            chargers,
        )


def collect(zcode: str = config.ZCODE) -> int:
    """zcode 지역의 충전소 정적 정보를 페이지네이션으로 전체 수집한다. 수집한 충전기 row 수를 반환."""
    page_no = 1
    total_items = 0
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
                },
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except ApiCallError as exc:
            db.log_api_call(API_NAME, None, False, note=str(exc))
            logger.error(
                "getChargerInfo page %s에서 중단 (지금까지 %s건은 저장됨): %s", page_no, total_items, exc
            )
            raise
        archive_raw(API_NAME, resp.text, "xml")
        result_code, items = _parse(resp.text)
        if result_code != "00":
            db.log_api_call(API_NAME, resp.status_code, False, note=f"resultCode={result_code}")
            raise RuntimeError(f"getChargerInfo 실패: resultCode={result_code}")

        fetched_at = db.now_iso()
        _upsert(items, fetched_at)
        db.log_api_call(API_NAME, resp.status_code, True, item_count=len(items))
        total_items += len(items)
        logger.info("getChargerInfo page %s: %s건 수집", page_no, len(items))

        if len(items) < PAGE_SIZE:
            break
        page_no += 1

    logger.info("getChargerInfo 총 %s건 수집 완료 (zcode=%s)", total_items, zcode)
    return total_items


def main() -> None:
    db.init_db()
    collect()


if __name__ == "__main__":
    main()
