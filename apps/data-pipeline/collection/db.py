"""수집 원본 데이터 SQLite 스키마 및 연결 헬퍼."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Iterator, Optional

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS charging_stations (
    stat_id      TEXT PRIMARY KEY,
    stat_nm      TEXT,
    addr         TEXT,
    lat          REAL,
    lng          REAL,
    busi_nm      TEXT,
    busi_call    TEXT,
    use_time     TEXT,
    parking_free TEXT,
    del_yn       TEXT,
    fetched_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chargers (
    stat_id          TEXT NOT NULL,
    chger_id         TEXT NOT NULL,
    chger_type       TEXT,
    output           TEXT,
    method           TEXT,
    stat             TEXT,
    stat_nm          TEXT,
    stat_updated_at  TEXT,
    fetched_at       TEXT NOT NULL,
    PRIMARY KEY (stat_id, chger_id)
);

CREATE TABLE IF NOT EXISTS kakao_places (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    stat_id              TEXT NOT NULL,
    category_group_code  TEXT NOT NULL,
    kakao_place_id       TEXT,
    place_name           TEXT,
    address_name         TEXT,
    distance_m           INTEGER,
    lat                  REAL,
    lng                  REAL,
    fetched_at           TEXT NOT NULL,
    UNIQUE(stat_id, category_group_code, kakao_place_id)
);

CREATE TABLE IF NOT EXISTS api_call_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    api_name     TEXT NOT NULL,
    called_at    TEXT NOT NULL,
    http_status  INTEGER,
    success      INTEGER NOT NULL,
    item_count   INTEGER,
    note         TEXT
);
"""


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(SCHEMA)


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def log_api_call(
    api_name: str,
    http_status: Optional[int],
    success: bool,
    item_count: Optional[int] = None,
    note: str = "",
) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO api_call_log (api_name, called_at, http_status, success, item_count, note) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (api_name, now_iso(), http_status, int(success), item_count, note),
        )


def calls_today(api_name: str) -> int:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM api_call_log "
            "WHERE api_name = ? AND date(called_at) = date('now', 'localtime')",
            (api_name,),
        ).fetchone()
        return row["cnt"] if row else 0


def ev_combined_calls_today() -> int:
    """getChargerInfo + getChargerStatus 합산 호출 수 (일 1,000건 한도 공동 관리)."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM api_call_log "
            "WHERE api_name IN ('ev_charger_info', 'ev_charger_status') "
            "AND date(called_at) = date('now', 'localtime')"
        ).fetchone()
        return row["cnt"] if row else 0
