from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ANALYSIS = Path(__file__).resolve().parents[2] / "processing" / "analysis"
if str(ANALYSIS) not in sys.path:
    sys.path.insert(0, str(ANALYSIS))

from build_arrival_availability_replay import (
    future_tick_map,
    nearest_neighbor_indices,
)


def test_future_tick_map_never_uses_current_tick() -> None:
    times = pd.DatetimeIndex(
        pd.to_datetime(
            [
                "2026-07-28 10:00:00",
                "2026-07-28 10:10:00",
                "2026-07-28 10:20:00",
            ]
        )
    )

    mapping = future_tick_map(times, 5)

    assert mapping.tolist() == [1, 2, -1]


def test_future_tick_map_does_not_cross_collection_gap() -> None:
    times = pd.DatetimeIndex(
        pd.to_datetime(
            [
                "2026-07-28 10:00:00",
                "2026-07-28 10:10:00",
                "2026-07-28 11:00:00",
            ]
        )
    )

    mapping = future_tick_map(times, 30, tolerance_minutes=30)

    assert mapping.tolist() == [-1, -1, -1]


def test_nearest_neighbors_exclude_self() -> None:
    lat = np.array([35.0, 35.0, 35.0])
    lng = np.array([128.0, 128.01, 128.02])

    neighbors = nearest_neighbor_indices(lat, lng, k=2)

    assert neighbors.shape == (3, 2)
    for index, row in enumerate(neighbors):
        assert index not in row
