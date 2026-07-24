from __future__ import annotations

from datetime import datetime

import pandas as pd

import reliability


def test_reliability_high_when_recent_update() -> None:
    base = datetime(2026, 7, 16, 14, 4, 0)
    df = pd.DataFrame([
        {"stat_id": "ST001", "stat_updated_at": "20260716140300"},
        {"stat_id": "ST001", "stat_updated_at": "20260716140000"},
    ])
    result = reliability.calculate_reliability(df, base)
    assert result.iloc[0]["reliability_grade"] == "HIGH"


def test_reliability_check_required_when_stale() -> None:
    base = datetime(2026, 7, 16, 14, 4, 0)
    df = pd.DataFrame([
        {"stat_id": "ST001", "stat_updated_at": "20260716120000"},
    ])
    result = reliability.calculate_reliability(df, base)
    assert result.iloc[0]["reliability_grade"] == "CHECK_REQUIRED"


def test_reliability_normal_in_middle_window() -> None:
    base = datetime(2026, 7, 16, 14, 4, 0)
    df = pd.DataFrame([
        {"stat_id": "ST001", "stat_updated_at": "20260716135500"},
    ])
    result = reliability.calculate_reliability(df, base)
    assert result.iloc[0]["reliability_grade"] == "NORMAL"
