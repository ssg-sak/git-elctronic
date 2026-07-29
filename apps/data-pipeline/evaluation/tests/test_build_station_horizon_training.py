from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ANALYSIS = Path(__file__).resolve().parents[2] / "processing" / "analysis"
if str(ANALYSIS) not in sys.path:
    sys.path.insert(0, str(ANALYSIS))

from build_station_horizon_training import (
    _change_features,
    assign_temporal_split,
    benjamini_hochberg,
    conservative_target,
)


def test_conservative_target_requires_full_coverage_for_negative() -> None:
    available = np.array([[1, 0, 0]], dtype=float)
    known = np.array([[1, 1, 2]], dtype=float)
    total = np.array([[2, 2, 2]], dtype=float)

    target, reason = conservative_target(available, known, total)

    assert target[0, 0] == 1
    assert np.isnan(target[0, 1])
    assert target[0, 2] == 0
    assert reason[0, 1] == "partial_unknown"
    assert reason[0, 2] == "full_coverage_negative"


def test_temporal_split_is_ordered_and_non_overlapping() -> None:
    dates = pd.Series(
        [
            "2026-07-22",
            "2026-07-23",
            "2026-07-24",
            "2026-07-25",
            "2026-07-26",
            "2026-07-27",
            "2026-07-28",
        ]
    )

    split = assign_temporal_split(dates)

    assert split.tolist() == [
        "train",
        "train",
        "train",
        "train",
        "valid",
        "test",
        "test",
    ]


def test_change_features_reset_after_unknown() -> None:
    times = pd.DatetimeIndex(
        pd.to_datetime(
            [
                "2026-07-28 10:00:00",
                "2026-07-28 10:10:00",
                "2026-07-28 10:20:00",
                "2026-07-28 10:30:00",
            ]
        )
    )
    available = np.array([[1], [1], [0], [2]], dtype=float)
    known = np.array([[1], [1], [0], [1]], dtype=float)

    delta, since = _change_features(times, available, known)

    assert np.isnan(delta[0, 0])
    assert delta[1, 0] == 0
    assert since[1, 0] == 10
    assert np.isnan(delta[2, 0])
    assert np.isnan(delta[3, 0])
    assert since[3, 0] == 0


def test_benjamini_hochberg_is_monotonic_in_sorted_p_values() -> None:
    adjusted = benjamini_hochberg([0.01, 0.02, 0.20, np.nan])

    assert adjusted[0] <= adjusted[1] <= adjusted[2]
    assert np.isnan(adjusted[3])
    assert adjusted[0] == 0.03
