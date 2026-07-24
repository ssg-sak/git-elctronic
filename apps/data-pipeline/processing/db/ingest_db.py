"""안전한 데이터 파일 유입 프로토콜 (ingest_db.py).

수집 담당자 등 외부로부터 제공받은 collection.db 파일을 검증, 백업 후 
원자적(Atomic)으로 활성 경로에 교체 반영합니다.
"""
from __future__ import annotations

import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

# 경로 설정 (db/ → processing/ → data-pipeline/collection)
import sys
from pathlib import Path
_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))
from _bootstrap import DATA_PIPELINE

COLLECTION_DIR = DATA_PIPELINE / "collection"
ACTIVE_DB_DIR = COLLECTION_DIR / "data"
ACTIVE_DB_PATH = ACTIVE_DB_DIR / "collection.db"

TEMP_DIR = ACTIVE_DB_DIR / "temp"
BACKUP_DIR = ACTIVE_DB_DIR / "backup"


def validate_db(db_path: Path) -> bool:
    """SQLite DB 파일의 무결성과 필수 테이블 존재 여부를 검증합니다."""
    if not db_path.exists():
        print(f"❌ 검증 실패: 파일이 존재하지 않습니다. ({db_path})")
        return False

    conn = None
    try:
        # SQLite 연결 시도 및 프라그마 체크
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA integrity_check")
        
        # 필수 테이블 존재 여부 확인
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = [row[0] for row in cursor.fetchall()]
        
        required_tables = ["charging_stations", "chargers"]
        for table in required_tables:
            if table not in tables:
                print(f"❌ 검증 실패: 필수 테이블 '{table}'이 누락되었습니다.")
                return False
                
        print("✅ DB 무결성 및 스키마 검증 통과")
        return True
    except sqlite3.Error as e:
        print(f"❌ 검증 실패: 올바르지 않은 SQLite DB 파일입니다. ({e})")
        return False
    finally:
        if conn:
            conn.close()


def ingest_database(source_path_str: str) -> bool:
    """공유받은 DB 파일을 임시 검증 공간(Staging)을 거쳐 백업 후 활성 DB로 교체합니다."""
    source_path = Path(source_path_str).resolve()
    
    if not source_path.exists():
        print(f"❌ 에러: 원본 파일 경로를 찾을 수 없습니다: {source_path}")
        return False

    # 디렉토리 생성
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ACTIVE_DB_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Staging: 임시 디렉토리에 먼저 복사
    temp_db_path = TEMP_DIR / "collection_staging.db"
    print(f"1. Staging 공간 복사 중... ({temp_db_path})")
    try:
        shutil.copy2(source_path, temp_db_path)
    except Exception as e:
        print(f"❌ 복사 중 에러 발생: {e}")
        return False

    # 2. 무결성 및 스키마 검증
    print("2. 무결성 검증 시작...")
    if not validate_db(temp_db_path):
        # 검증 실패 시 임시 파일 삭제
        if temp_db_path.exists():
            temp_db_path.unlink()
        return False

    # 3. 기존 파일 백업
    if ACTIVE_DB_PATH.exists():
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = BACKUP_DIR / f"collection_backup_{timestamp}.db"
        print(f"3. 기존 활성 DB 백업 중... ({backup_path})")
        try:
            shutil.copy2(ACTIVE_DB_PATH, backup_path)
        except Exception as e:
            print(f"❌ 백업 생성 실패 (작업 계속 진행): {e}")

    # 4. 원자적 교체 (Atomic Rename / Replace)
    print(f"4. 활성 경로 DB 교체 중... ({ACTIVE_DB_PATH})")
    try:
        # 기존 파일 위에 덮어쓰기 형태로 원자적 이동
        if ACTIVE_DB_PATH.exists():
            ACTIVE_DB_PATH.unlink()
        temp_db_path.rename(ACTIVE_DB_PATH)
        print("🎉 데이터베이스 유입 및 안전 반영 완료!")
        return True
    except Exception as e:
        print(f"❌ 활성 경로 반영 중 에러 발생: {e}")
        return False


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("사용법: python ingest_db.py <공유받은_db_파일_경로>")
        sys.exit(1)
        
    success = ingest_database(sys.argv[1])
    sys.exit(0 if success else 1)
