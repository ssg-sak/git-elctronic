"""카카오 로컬 API 수집기: 충전소 주변 편의시설(카페·음식점·편의점) 수집, 1일 1회.

charging_stations 테이블(= getChargerInfo 수집 결과)을 기준으로 각 충전소 주변을 검색한다.
따라서 getChargerInfo를 먼저 실행해 충전소 목록을 채워둬야 한다.

단독 실행: python kakao_local.py
"""
from __future__ import annotations

import config
import db
from http_client import ApiCallError, archive_raw, request_with_retry
from logging_conf import get_logger

logger = get_logger(__name__)

BASE_URL = "https://dapi.kakao.com/v2/local/search/category.json"
API_NAME = "kakao_local"
CATEGORY_CODES = {
    "CE7": "카페",
    "FD6": "음식점",
    "CS2": "편의점",
}
SEARCH_RADIUS_M = 500


def _fetch_category(lat: float, lng: float, category_code: str) -> list[dict]:
    """충전소 하나 x 카테고리 하나 조회. 실패해도 나머지 충전소 수집은 계속 진행한다."""
    try:
        resp = request_with_retry(
            "GET",
            BASE_URL,
            params={
                "category_group_code": category_code,
                "x": lng,
                "y": lat,
                "radius": SEARCH_RADIUS_M,
                "sort": "distance",
            },
            headers={"Authorization": f"KakaoAK {config.KAKAO_REST_KEY}"},
        )
    except ApiCallError as exc:
        db.log_api_call(API_NAME, None, False, note=str(exc))
        logger.error("카카오 로컬 조회 실패(lat=%s, lng=%s, category=%s): %s", lat, lng, category_code, exc)
        return []
    archive_raw(API_NAME, resp.text, "json")
    data = resp.json()
    documents = data.get("documents", [])
    db.log_api_call(API_NAME, resp.status_code, True, item_count=len(documents))
    return documents


def _upsert_places(stat_id: str, category_code: str, documents: list[dict], fetched_at: str) -> None:
    if not documents:
        return
    rows = [
        (
            stat_id,
            category_code,
            doc.get("id"),
            doc.get("place_name"),
            doc.get("address_name"),
            int(doc["distance"]) if doc.get("distance") else None,
            float(doc["y"]) if doc.get("y") else None,
            float(doc["x"]) if doc.get("x") else None,
            fetched_at,
        )
        for doc in documents
    ]
    with db.get_connection() as conn:
        conn.executemany(
            """
            INSERT INTO kakao_places
                (stat_id, category_group_code, kakao_place_id, place_name, address_name, distance_m, lat, lng, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(stat_id, category_group_code, kakao_place_id) DO UPDATE SET
                place_name=excluded.place_name, address_name=excluded.address_name,
                distance_m=excluded.distance_m, lat=excluded.lat, lng=excluded.lng, fetched_at=excluded.fetched_at
            """,
            rows,
        )


def _active_stations() -> list[tuple[str, float, float]]:
    with db.get_connection() as conn:
        rows = conn.execute(
            "SELECT stat_id, lat, lng FROM charging_stations "
            "WHERE lat IS NOT NULL AND lng IS NOT NULL AND (del_yn IS NULL OR del_yn != 'Y')"
        ).fetchall()
    return [(r["stat_id"], r["lat"], r["lng"]) for r in rows]


def collect() -> int:
    """충전소별 주변 편의시설을 카테고리별로 수집한다. 총 수집 건수를 반환."""
    stations = _active_stations()
    if not stations:
        logger.warning("charging_stations가 비어 있음 — ev_charger_info.collect()를 먼저 실행하세요")
        return 0

    total = 0
    fetched_at = db.now_iso()
    for stat_id, lat, lng in stations:
        for category_code in CATEGORY_CODES:
            documents = _fetch_category(lat, lng, category_code)
            _upsert_places(stat_id, category_code, documents, fetched_at)
            total += len(documents)

    logger.info(
        "카카오 로컬 수집 완료: 충전소 %s곳 x 카테고리 %s개, 총 %s건", len(stations), len(CATEGORY_CODES), total
    )
    return total


def main() -> None:
    db.init_db()
    collect()


if __name__ == "__main__":
    main()
