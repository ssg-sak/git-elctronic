"""수집 파이프라인 공통 설정. 루트 .env를 읽는다."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

COLLECTION_DIR = Path(__file__).resolve().parent
ROOT_DIR = COLLECTION_DIR.parents[2]
RAW_DIR = COLLECTION_DIR / "raw"
DATA_DIR = COLLECTION_DIR / "data"
DB_PATH = DATA_DIR / "collection.db"

load_dotenv(ROOT_DIR / ".env")

DATA_GO_KR_KEY = os.environ["DATA_GO_KR_KEY"]
KAKAO_REST_KEY = os.environ["KAKAO_REST_KEY"]

# MVP 대상 지역: 대구광역시 (EvCharger zcode)
ZCODE = "27"

# 대구 중심 좌표 (동성로 인근)
DAEGU_CENTER_LAT = 35.8714
DAEGU_CENTER_LNG = 128.6014

# getChargerStatus: 스케줄 간격(분) · API period(분, 공식 max 10)
STATUS_INTERVAL_MINUTES = 5
STATUS_PERIOD_MINUTES = 10

# EvCharger 일 트래픽 한도 (AGENTS.md 기준, getChargerInfo/Status 합산으로 보수적으로 관리)
EV_API_DAILY_LIMIT = 1000

REQUEST_TIMEOUT_SECONDS = 60
MAX_RETRIES = 2
RETRY_BACKOFF_SECONDS = 3

RAW_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)
