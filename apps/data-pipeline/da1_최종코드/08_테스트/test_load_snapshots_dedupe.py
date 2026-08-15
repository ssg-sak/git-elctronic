from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

LOADER_DIR = (
    Path(__file__).resolve().parents[1]
    / "personal"
    / "experiments"
    / "SANDBOX_20260717_status_periodic_collection"
    / "src"
)
if str(LOADER_DIR) not in sys.path:
    sys.path.insert(0, str(LOADER_DIR))

from load_snapshots import _dedupe_snapshot_rows


def test_page_boundary_duplicate_keeps_latest_status_event() -> None:
    frame = pd.DataFrame(
        [
            {
                "snapshotId": "20260723_103617",
                "statId": "JA270010",
                "chgerId": "01",
                "stat": "5",
                "statUpdDt": "20260723103017",
                "pageNo": "4",
            },
            {
                "snapshotId": "20260723_103617",
                "statId": "JA270010",
                "chgerId": "01",
                "stat": "2",
                "statUpdDt": "20260723103512",
                "pageNo": "5",
            },
        ]
    )

    result = _dedupe_snapshot_rows(frame)

    assert len(result) == 1
    assert result.iloc[0]["stat"] == "2"
    assert result.iloc[0]["statUpdDt"] == "20260723103512"


def test_same_charger_in_different_snapshots_is_preserved() -> None:
    frame = pd.DataFrame(
        [
            {
                "snapshotId": "20260723_103617",
                "statId": "A",
                "chgerId": "01",
                "stat": "2",
                "statUpdDt": "20260723103512",
                "pageNo": "1",
            },
            {
                "snapshotId": "20260723_104617",
                "statId": "A",
                "chgerId": "01",
                "stat": "3",
                "statUpdDt": "20260723104512",
                "pageNo": "1",
            },
        ]
    )

    result = _dedupe_snapshot_rows(frame)

    assert len(result) == 2
