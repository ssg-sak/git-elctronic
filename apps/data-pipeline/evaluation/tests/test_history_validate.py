"""Tests for history validation (DATA_PART_WORK_GUIDE §4.4)."""
from __future__ import annotations

import pytest
import pandas as pd

from history_validate import validate_history


def test_validate_history_ok():
    df = pd.DataFrame(
        [
            {
                "observedAt": "2026-07-20T10:00:00+09:00",
                "stationId": "S1",
                "chargerId": "01",
                "status": "AVAILABLE",
            }
        ]
    )
    df["observedAt"] = pd.to_datetime(df["observedAt"])
    report = validate_history(df)
    assert report["rows"] == 1
    assert report["invalid_status_rows"] == 0


def test_validate_history_missing_column():
    df = pd.DataFrame([{"stationId": "S1"}])
    with pytest.raises(ValueError, match="필수 컬럼"):
        validate_history(df)
