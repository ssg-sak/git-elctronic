"""충전소 단위 집계 모듈 (aggregation.py).

개별 충전기 상태 데이터를 충전소 기준으로 집계합니다.
"""
from __future__ import annotations

import pandas as pd


def aggregate_chargers(df_chargers: pd.DataFrame) -> pd.DataFrame:
    """정제된 chargers 데이터를 충전소(stat_id) 단위로 집계합니다.
    
    집계 컬럼:
    1. total_chargers: 충전소의 전체 충전기 개수
    2. available_chargers: 사용 가능한 충전기 개수 (stat == 'AVAILABLE')
    
    반환 DataFrame 스키마:
    - stat_id (index 또는 column)
    - total_chargers
    - available_chargers
    """
    if df_chargers.empty:
        return pd.DataFrame(columns=["stat_id", "total_chargers", "available_chargers"])

    df = df_chargers.copy()

    # 충전소(stat_id)별 전체 충전기 개수 계산
    total_counts = df.groupby("stat_id").size().rename("total_chargers")

    # 사용 가능한 충전기 개수 계산 (stat == 'AVAILABLE')
    available_mask = df["stat"] == "AVAILABLE"
    available_counts = df[available_mask].groupby("stat_id").size().rename("available_chargers")

    # 두 집계 데이터 병합
    agg_df = pd.concat([total_counts, available_counts], axis=1).fillna(0)
    agg_df["total_chargers"] = agg_df["total_chargers"].astype(int)
    agg_df["available_chargers"] = agg_df["available_chargers"].astype(int)

    # index를 column으로 변환
    agg_df = agg_df.reset_index()

    return agg_df
