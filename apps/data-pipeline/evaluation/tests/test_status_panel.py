"""Unit tests for gap-safe status panel reconstruction."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

EVAL_DIR = Path(__file__).resolve().parent.parent
STATUS_SRC = (
    EVAL_DIR
    / "personal"
    / "experiments"
    / "SANDBOX_20260717_status_periodic_collection"
    / "src"
)
sys.path.insert(0, str(STATUS_SRC))

from build_panel import availability_timeseries, build_state_panel  # noqa: E402


def _observations(rows: list[tuple[str, str, str, int]]) -> pd.DataFrame:
    return pd.DataFrame(
        rows,
        columns=["snapshotId", "statId", "chgerId", "stat"],
    )


def test_forward_fill_never_leaks_future_state_backward() -> None:
    source = _observations(
        [
            ("20260719_080000", "A", "01", 2),
            ("20260719_081500", "B", "01", 3),
            ("20260719_083000", "A", "01", 3),
        ]
    )

    panel = build_state_panel(source)
    a = "A|01"
    b = "B|01"

    assert panel.loc["2026-07-19 08:00:00", a] == 2
    assert pd.isna(panel.loc["2026-07-19 08:00:00", b])
    assert panel.loc["2026-07-19 08:15:00", a] == 2
    assert panel.loc["2026-07-19 08:15:00", b] == 3
    assert panel.loc["2026-07-19 08:30:00", a] == 3


def test_each_known_charger_has_equal_weight_at_each_snapshot() -> None:
    source = _observations(
        [
            ("20260719_080000", "A", "01", 2),
            ("20260719_080000", "B", "01", 3),
            # Only A changes/appears at 08:15. B must still count once as in-use.
            ("20260719_081500", "A", "01", 2),
        ]
    )

    ts = availability_timeseries(build_state_panel(source))

    assert ts["usable_known"].tolist() == [2, 2]
    assert ts["availability_pct"].tolist() == pytest.approx([50.0, 50.0])


def test_state_is_not_carried_across_collection_gap() -> None:
    source = _observations(
        [
            ("20260719_080000", "A", "01", 2),
            ("20260719_082500", "B", "01", 3),  # exactly 25 min: continuous
            ("20260719_085100", "B", "01", 2),  # 26 min: new segment
        ]
    )

    panel = build_state_panel(source, max_continuous_gap_minutes=25)
    a = "A|01"
    b = "B|01"

    assert panel.loc["2026-07-19 08:25:00", a] == 2
    assert panel.loc["2026-07-19 08:25:00", b] == 3
    assert pd.isna(panel.loc["2026-07-19 08:51:00", a])
    assert panel.loc["2026-07-19 08:51:00", b] == 2


def test_non_usable_states_are_excluded_from_availability_denominator() -> None:
    source = _observations(
        [
            ("20260719_080000", "A", "01", 2),
            ("20260719_080000", "B", "01", 3),
            ("20260719_080000", "C", "01", 5),
        ]
    )

    ts = availability_timeseries(build_state_panel(source))

    assert ts.loc[0, "available"] == 1
    assert ts.loc[0, "in_use"] == 1
    assert ts.loc[0, "usable_known"] == 2
    assert ts.loc[0, "availability_pct"] == pytest.approx(50.0)
