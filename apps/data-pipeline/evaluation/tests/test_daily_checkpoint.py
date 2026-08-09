"""Unit tests for daily collection timing checks."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

EVAL_DIR = Path(__file__).resolve().parent.parent
STATUS_SRC = (
    EVAL_DIR
    / "personal"
    / "experiments"
    / "SANDBOX_20260717_status_periodic_collection"
    / "src"
)
sys.path.insert(0, str(STATUS_SRC))

from daily_checkpoint import _timing_metrics  # noqa: E402


def test_continuous_five_minute_collection_is_healthy() -> None:
    # EXPECTED_INTERVAL_MINUTES = 5 in daily_checkpoint
    times = pd.Series(
        pd.to_datetime(
            [
                "2026-07-19 08:00:00",
                "2026-07-19 08:05:00",
                "2026-07-19 08:10:00",
            ]
        )
    )

    metrics = _timing_metrics(times)

    assert metrics["interval_median_minutes"] == 5.0
    assert metrics["continuity_pct_within_active_span"] == 100.0
    assert metrics["gap_count"] == 0


def test_long_gap_is_reported_with_estimated_missed_rounds() -> None:
    times = pd.Series(
        pd.to_datetime(
            [
                "2026-07-19 08:00:00",
                "2026-07-19 08:05:00",
                "2026-07-19 08:50:00",
            ]
        )
    )

    metrics = _timing_metrics(times)

    assert metrics["gap_count"] == 1
    assert metrics["gaps"][0]["minutes"] == 45.0
    # missed rounds ≈ round(45/5) - 1
    assert metrics["gaps"][0]["approx_missed"] == 8
