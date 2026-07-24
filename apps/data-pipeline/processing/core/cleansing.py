"""데이터 정제 모듈 (cleansing.py).

원본 충전소 및 충전기 데이터를 정제하고 코드 매핑을 수행합니다.
"""
from __future__ import annotations

import pandas as pd

# 충전기 타입 매핑 (원본 코드 -> 표준 한글명)
CHGER_TYPE_MAP = {
    "01": "DC차데모",
    "02": "AC완속",
    "03": "DC차데모+AC3상",
    "04": "DC콤보",
    "05": "DC차데모+DC콤보",
    "06": "DC차데모+AC3상+DC콤보",
    "07": "AC3상",
    "08": "DC콤보(완속)",
    "10": "초급속(멀티)",
    # EvCharger 원천에 등장 (대구 info 2026-07-23: 5대, output≈120kW). 공식명 확정 전 잠정.
    "11": "초급속(미확인규격)",
}

# 상태 코드 매핑 (원본 코드 -> 표준 영문 코드)
# 정본: docs/data/스키마/상태코드_매핑.md
STAT_MAP = {
    "1": "UNKNOWN",  # 통신이상 → 미확인
    "2": "AVAILABLE",  # 충전대기 → 사용 가능
    "3": "CHARGING",  # 충전중 → 사용 중
    "4": "OUT_OF_ORDER",  # 운영중지 → 고장
    "5": "UNDER_INSPECTION",  # 점검중 → 점검
    "9": "UNKNOWN",  # 상태미확인
    "01": "UNKNOWN",
    "02": "AVAILABLE",
    "03": "CHARGING",
    "04": "OUT_OF_ORDER",
    "05": "UNDER_INSPECTION",
    "09": "UNKNOWN",
}


def clean_stations(df: pd.DataFrame) -> pd.DataFrame:
    """charging_stations 원본 데이터를 정제합니다.
    
    정제 규칙:
    1. lat (위도) 유효성 검증: 35.6 <= lat <= 36.2
    2. lng (경도) 유효성 검증: 128.3 <= lng <= 128.9
    3. stat_nm, addr가 결측치거나 공백만 있는 행은 드롭
    """
    if df.empty:
        return df

    # 결측치 방지 및 공백 제거
    df = df.copy()
    
    # 1. 필수 필드 결측치 검증
    df = df.dropna(subset=["stat_id", "stat_nm", "addr"])
    
    df["stat_nm"] = df["stat_nm"].astype(str).str.strip()
    df["addr"] = df["addr"].astype(str).str.strip()
    
    # 빈 문자열 드롭
    df = df[(df["stat_nm"] != "") & (df["addr"] != "")]

    # 2. 좌표 수치 데이터 변환 및 결측치 드롭
    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    df["lng"] = pd.to_numeric(df["lng"], errors="coerce")
    df = df.dropna(subset=["lat", "lng"])

    # 3. 대구 범위 검증
    lat_mask = (df["lat"] >= 35.6) & (df["lat"] <= 36.2)
    lng_mask = (df["lng"] >= 128.3) & (df["lng"] <= 128.9)
    df = df[lat_mask & lng_mask]

    # 기타 필드 정규화
    df["busi_nm"] = df["busi_nm"].fillna("").astype(str).str.strip()
    df["use_time"] = df["use_time"].fillna("24시간 이용가능").astype(str).str.strip()
    df["parking_free"] = df["parking_free"].fillna("N").astype(str).str.strip().str.upper()

    return df


def clean_chargers(df: pd.DataFrame) -> pd.DataFrame:
    """chargers 원본 데이터를 정제하고 코드를 매핑합니다.
    
    정제 규칙:
    1. chger_type 코드를 표준 한글명으로 매핑 (누락 시 '알수없음')
    2. stat 코드를 표준 상태로 매핑 (AVAILABLE, CHARGING, OUT_OF_ORDER, UNDER_INSPECTION, UNKNOWN)
       — docs/data/스키마/상태코드_매핑.md 정본
    """
    if df.empty:
        return df

    df = df.copy()
    
    # 필수 필드 드롭
    df = df.dropna(subset=["stat_id", "chger_id"])

    # 1. 충전기 타입 매핑
    df["chger_type"] = df["chger_type"].astype(str).str.strip()
    df["chger_type"] = df["chger_type"].map(CHGER_TYPE_MAP).fillna("알수없음")

    # 2. 상태 코드 매핑
    df["stat"] = df["stat"].astype(str).str.strip()
    df["stat"] = df["stat"].map(STAT_MAP).fillna("UNKNOWN")

    # 3. 충전 용량 및 기타 필드 정규화
    df["output"] = df["output"].fillna("").astype(str).str.strip()
    df["stat_updated_at"] = df["stat_updated_at"].fillna("").astype(str).str.strip()

    return df
