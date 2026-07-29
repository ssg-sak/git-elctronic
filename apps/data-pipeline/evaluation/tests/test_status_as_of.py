"""Tests for as-of status selection (D1 refresh)."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from status_as_of import join_master_with_status, load_latest_status_as_of

KST = ZoneInfo("Asia/Seoul")


def test_as_of_picks_newest_not_future(tmp_path: Path):
    rows = [
        {
            "statId": "A",
            "chgerId": "01",
            "stat": "2",
            "statUpdDt": "20260720120000",
            "fetchedAt": "2026-07-20 12:00:00",
            "snapshotId": "20260720_120000",
            "pageNo": "1",
        },
        {
            "statId": "A",
            "chgerId": "01",
            "stat": "3",
            "statUpdDt": "20260720130000",
            "fetchedAt": "2026-07-20 13:00:00",
            "snapshotId": "20260720_130000",
            "pageNo": "1",
        },
        {
            "statId": "A",
            "chgerId": "01",
            "stat": "2",
            "statUpdDt": "20260720140000",  # after as_of → ignored
            "fetchedAt": "2026-07-20 14:00:00",
            "snapshotId": "20260720_140000",
            "pageNo": "1",
        },
    ]
    for r in rows:
        fp = tmp_path / f"daegu_charger_status_{r['snapshotId']}.csv"
        pd.DataFrame([r]).to_csv(fp, index=False)

    as_of = datetime(2026, 7, 20, 13, 30, tzinfo=KST)
    out = load_latest_status_as_of(tmp_path, as_of)
    assert len(out) == 1
    assert out.iloc[0]["stat_mapped"] == "CHARGING"
    assert out.iloc[0]["snapshotId"] == "20260720_130000"
    # age ≈ 30 minutes
    assert 29 * 60 <= float(out.iloc[0]["status_age_seconds"]) <= 31 * 60


def test_last_seen_improves_observation_age(tmp_path: Path):
    """Same statUpdDt in two polls → observation_age < status_age."""
    base = {
        "statId": "A",
        "chgerId": "01",
        "stat": "2",
        "statUpdDt": "20260720120000",
    }
    rows = [
        {**base, "fetchedAt": "2026-07-20 12:05:00", "snapshotId": "20260720_120500", "pageNo": "1"},
        {**base, "fetchedAt": "2026-07-20 12:20:00", "snapshotId": "20260720_122000", "pageNo": "1"},
    ]
    for r in rows:
        fp = tmp_path / f"daegu_charger_status_{r['snapshotId']}.csv"
        pd.DataFrame([r]).to_csv(fp, index=False)

    as_of = datetime(2026, 7, 20, 12, 25, tzinfo=KST)
    out = load_latest_status_as_of(tmp_path, as_of)
    assert len(out) == 1
    assert 24 * 60 <= float(out.iloc[0]["status_age_seconds"]) <= 26 * 60
    assert 4 * 60 <= float(out.iloc[0]["observation_age_seconds"]) <= 6 * 60


def test_same_snapshot_page_boundary_duplicate_keeps_newest_event(tmp_path: Path):
    """A charger can move across API pages while one snapshot is collected."""
    snapshot_id = "20260723_103617"
    rows = [
        {
            "statId": "JA270010",
            "chgerId": "01",
            "stat": "5",
            "statUpdDt": "20260723103017",
            "fetchedAt": "2026-07-23 10:36:17",
            "snapshotId": snapshot_id,
            "pageNo": "4",
        },
        {
            "statId": "JA270010",
            "chgerId": "01",
            "stat": "2",
            "statUpdDt": "20260723103512",
            "fetchedAt": "2026-07-23 10:36:17",
            "snapshotId": snapshot_id,
            "pageNo": "5",
        },
    ]
    pd.DataFrame(rows).to_csv(
        tmp_path / f"daegu_charger_status_{snapshot_id}.csv",
        index=False,
    )

    as_of = datetime(2026, 7, 23, 10, 37, tzinfo=KST)
    out = load_latest_status_as_of(tmp_path, as_of)

    assert len(out) == 1
    assert out.iloc[0]["stat"] == 2
    assert out.iloc[0]["stat_mapped"] == "AVAILABLE"
    assert out.iloc[0]["statUpdDt_dt"] == pd.Timestamp(
        "2026-07-23 10:35:12",
        tz=KST,
    )


def test_join_marks_missing_status():
    master = pd.DataFrame(
        [
            {"statId": "A", "chgerId": "01", "pk": "A|01"},
            {"statId": "A", "chgerId": "02", "pk": "A|02"},
        ]
    )
    status = pd.DataFrame(
        [
            {
                "statId": "A",
                "chgerId": "01",
                "pk": "A|01",
                "stat": "2",
                "stat_mapped": "AVAILABLE",
                "statUpdDt_dt": datetime(2026, 7, 20, 13, 0, tzinfo=KST),
                "status_age_seconds": 60.0,
                "snapshotId": "x",
            }
        ]
    )
    view = join_master_with_status(master, status)
    assert bool(view.loc[view["chgerId"] == "01", "status_missing"].iloc[0]) is False
    assert bool(view.loc[view["chgerId"] == "02", "status_missing"].iloc[0]) is True
    assert view.loc[view["chgerId"] == "02", "availability_note"].iloc[0] == "NO_STATUS_OBSERVED"
