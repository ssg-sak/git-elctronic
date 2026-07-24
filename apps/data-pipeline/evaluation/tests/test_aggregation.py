from __future__ import annotations

import pandas as pd

import aggregation


def test_aggregate_counts_available() -> None:
    df = pd.DataFrame([
        {"stat_id": "ST001", "stat": "AVAILABLE"},
        {"stat_id": "ST001", "stat": "CHARGING"},
        {"stat_id": "ST001", "stat": "AVAILABLE"},
    ])
    agg = aggregation.aggregate_chargers(df)
    row = agg[agg["stat_id"] == "ST001"].iloc[0]
    assert row["total_chargers"] == 3
    assert row["available_chargers"] == 2
