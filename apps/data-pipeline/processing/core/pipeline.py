"""가공 파이프라인 연동 모듈 (pipeline.py).

정제, 집계, 신뢰도 평가 단계를 통합하여 processed_stations 및 processed_chargers 테이블에 적재합니다.
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime
from pathlib import Path
import pandas as pd

# 모듈 경로 추가 (processing -> collection)
import sys
from pathlib import Path
_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))
from _bootstrap import PROCESSING, ensure_paths

ensure_paths()
PROCESSING_DIR = PROCESSING
COLLECTION_DIR = PROCESSING_DIR.parent / "collection"
sys.path.append(str(COLLECTION_DIR))

import config
import db
from core import aggregation, cleansing, reliability

# 가공 테이블 생성 스키마
PROCESSED_SCHEMA = """
CREATE TABLE IF NOT EXISTS processed_stations (
    stat_id            TEXT PRIMARY KEY,
    stat_nm            TEXT NOT NULL,
    addr               TEXT NOT NULL,
    lat                REAL NOT NULL,
    lng                REAL NOT NULL,
    total_chargers     INTEGER NOT NULL,
    available_chargers INTEGER NOT NULL,
    reliability_grade  TEXT NOT NULL,
    updated_at         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS processed_chargers (
    stat_id          TEXT NOT NULL,
    chger_id         TEXT NOT NULL,
    chger_type       TEXT NOT NULL,
    output           TEXT NOT NULL,
    stat             TEXT NOT NULL,
    stat_updated_at  TEXT NOT NULL,
    PRIMARY KEY (stat_id, chger_id),
    FOREIGN KEY (stat_id) REFERENCES processed_stations(stat_id) ON DELETE CASCADE
);
"""


def init_processed_tables(conn: sqlite3.Connection) -> None:
    """가공 완료 서비스 테이블을 초기화합니다."""
    conn.executescript(PROCESSED_SCHEMA)


def run_pipeline() -> None:
    """전체 가공 파이프라인을 실행합니다."""
    print("가공 파이프라인 시작...")
    
    # 기준 시각 설정
    now = datetime.now().astimezone()
    updated_at_iso = now.isoformat(timespec="seconds")

    with db.get_connection() as conn:
        # 0. 가공 테이블 초기화
        init_processed_tables(conn)

        # 1. 원본 데이터 로딩
        print("원본 데이터 읽는 중...")
        try:
            df_stations_raw = pd.read_sql_query("SELECT * FROM charging_stations", conn)
            df_chargers_raw = pd.read_sql_query("SELECT * FROM chargers", conn)
        except Exception as exc:
            print(f"오류: 원본 테이블 로딩 실패 (수집기를 먼저 실행했는지 확인하세요): {exc}")
            raise

        if df_stations_raw.empty or df_chargers_raw.empty:
            print("경고: 원본 데이터가 비어 있습니다. 가공을 중단합니다.")
            return

        # 2. 데이터 정제 (Cleansing)
        print("데이터 정제 진행 중...")
        df_stations_clean = cleansing.clean_stations(df_stations_raw)
        df_chargers_clean = cleansing.clean_chargers(df_chargers_raw)

        # 3. 충전소 단위 집계 (Aggregation)
        print("충전소 단위 집계 진행 중...")
        df_agg = aggregation.aggregate_chargers(df_chargers_clean)

        # 4. 신뢰도 평가 (Reliability)
        print("신뢰도 등급 계산 중...")
        df_rel = reliability.calculate_reliability(df_chargers_clean, now)

        # 5. 충전소 데이터 병합
        print("가공 결과 병합 중...")
        # 정제된 충전소 기준, 집계 및 신뢰도 데이터를 좌측 병합
        df_stations_processed = df_stations_clean[["stat_id", "stat_nm", "addr", "lat", "lng"]].copy()
        
        # 집계 정보 병합 (집계가 없는 경우 0대 처리)
        df_stations_processed = df_stations_processed.merge(df_agg, on="stat_id", how="left")
        df_stations_processed["total_chargers"] = df_stations_processed["total_chargers"].fillna(0).astype(int)
        df_stations_processed["available_chargers"] = df_stations_processed["available_chargers"].fillna(0).astype(int)
        
        # 신뢰도 정보 병합 (신뢰도가 없는 경우 CHECK_REQUIRED 처리)
        df_stations_processed = df_stations_processed.merge(df_rel, on="stat_id", how="left")
        df_stations_processed["reliability_grade"] = df_stations_processed["reliability_grade"].fillna("CHECK_REQUIRED")
        
        # 가공 완료 일시 추가
        df_stations_processed["updated_at"] = updated_at_iso

        # 6. 정제된 충전기 데이터 필터링
        # 정제된 충전소(유효 좌표/주소)에 속한 충전기만 저장
        valid_station_ids = set(df_stations_processed["stat_id"])
        df_chargers_processed = df_chargers_clean[df_chargers_clean["stat_id"].isin(valid_station_ids)].copy()
        df_chargers_processed = df_chargers_processed[[
            "stat_id", "chger_id", "chger_type", "output", "stat", "stat_updated_at"
        ]]

        # 7. DB 적재 (기존 가공 테이블 데이터 비우고 적재)
        print("서비스 테이블 적재 중...")
        conn.execute("DELETE FROM processed_stations")
        conn.execute("DELETE FROM processed_chargers")

        # to_sql 시 스키마 충돌 방지 및 트랜잭션 보장을 위해 append 사용
        df_stations_processed.to_sql(
            "processed_stations", conn, if_exists="append", index=False
        )
        df_chargers_processed.to_sql(
            "processed_chargers", conn, if_exists="append", index=False
        )

        print(f"가공 완료: processed_stations ({len(df_stations_processed)}건), processed_chargers ({len(df_chargers_processed)}건) 적재 성공!")


if __name__ == "__main__":
    try:
        run_pipeline()
    except Exception as e:
        print(f"파이프라인 실행 중 오류 발생: {e}")
        sys.exit(1)
