"""신뢰도 계산 모듈 (reliability.py).

충전기 상태 최종 변경 시각(stat_updated_at)을 비교하여 충전소 단위 신뢰도 등급을 계산합니다.
"""
from __future__ import annotations

from datetime import datetime
import pandas as pd


def calculate_minutes_elapsed(stat_updated_at_str: str, base_time: datetime) -> float:
    """stat_updated_at (YYYYMMDDHHmmss)과 base_time 간의 시간 차이(분)를 계산합니다.
    
    잘못된 포맷이거나 누락된 경우 무한대(inf)를 반환하여 신뢰도가 낮음으로 평가되도록 합니다.
    """
    if not isinstance(stat_updated_at_str, str) or not stat_updated_at_str or len(stat_updated_at_str) != 14:
        return float("inf")

    try:
        dt = datetime.strptime(stat_updated_at_str, "%Y%m%d%H%M%S")
        # base_time이 tz-aware인 경우 dt도 tz-aware로 맞추거나, 둘 다 naive로 통일
        if base_time.tzinfo is not None:
            # naive datetime을 local tz-aware로 변환
            dt = dt.astimezone(base_time.tzinfo)
        diff = base_time - dt
        return diff.total_seconds() / 60.0
    except Exception:
        return float("inf")


def calculate_reliability(df_chargers: pd.DataFrame, base_time: datetime) -> pd.DataFrame:
    """정제된 chargers 데이터를 바탕으로 충전소별 신뢰도 등급을 계산합니다.
    
    신뢰도 등급 규칙:
    - HIGH (높음): 충전기들의 상태 갱신 시각 중 가장 최근 시각의 경과 시간이 5분 이내
    - NORMAL (보통): 5분 초과 ~ 15분 이내
    - CHECK_REQUIRED (확인필요): 15분 초과 또는 정보 누락
    
    반환 DataFrame 스키마:
    - stat_id (index 또는 column)
    - reliability_grade
    """
    if df_chargers.empty:
        return pd.DataFrame(columns=["stat_id", "reliability_grade"])

    df = df_chargers.copy()

    # 각 충전기별 경과 시간(분) 계산
    df["elapsed_minutes"] = df["stat_updated_at"].apply(
        lambda x: calculate_minutes_elapsed(x, base_time)
    )

    # 충전소(stat_id)별로 그룹화하여 가장 최신의 갱신 상태(최소 경과 시간)를 구함
    min_elapsed = df.groupby("stat_id")["elapsed_minutes"].min().reset_index()

    # 경과 시간 기준 등급 부여
    def get_grade(minutes: float) -> str:
        if minutes <= 5.0:
            return "HIGH"
        elif minutes <= 15.0:
            return "NORMAL"
        else:
            return "CHECK_REQUIRED"

    min_elapsed["reliability_grade"] = min_elapsed["elapsed_minutes"].apply(get_grade)
    
    # 불필요한 컬럼 제거하고 반환
    return min_elapsed[["stat_id", "reliability_grade"]]
