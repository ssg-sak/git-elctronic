"""Tests for gap-safe panel (DATA_PART_WORK_GUIDE §4.5)."""
from __future__ import annotations

import pandas as pd

from gap_safe_panel import build_gap_safe_panel


def _events(rows):
    return pd.DataFrame(rows)


def test_no_future_status_at_past_panel_ts():
    events = _events(
        [
            {
                "stationId": "S1",
                "chargerId": "01",
                "status": "AVAILABLE",
                "observedAt": "2026-07-20T10:00:00+09:00",
            },
            {
                "stationId": "S1",
                "chargerId": "01",
                "status": "CHARGING",
                "observedAt": "2026-07-20T10:30:00+09:00",
            },
        ]
    )
    panel = build_gap_safe_panel(events, max_gap_minutes=25)
    at_10 = panel[panel["panel_ts"] == pd.Timestamp("2026-07-20T10:00:00+09:00")]
    assert len(at_10) == 1
    assert at_10.iloc[0]["status"] == "AVAILABLE"


def test_gap_over_25min_resets_segment():
    events = _events(
        [
            {
                "stationId": "S1",
                "chargerId": "01",
                "status": "AVAILABLE",
                "observedAt": "2026-07-20T10:00:00+09:00",
            },
            {
                "stationId": "S1",
                "chargerId": "01",
                "status": "CHARGING",
                "observedAt": "2026-07-20T11:00:00+09:00",
            },
        ]
    )
    panel = build_gap_safe_panel(events, max_gap_minutes=25)
    at_11 = panel[panel["panel_ts"] == pd.Timestamp("2026-07-20T11:00:00+09:00")]
    assert at_11.iloc[0]["status"] == "CHARGING"
    assert at_11.iloc[0]["segment_id"] != panel.iloc[0]["segment_id"]


def test_one_row_per_charger_per_timestamp():
    events = _events(
        [
            {
                "stationId": "S1",
                "chargerId": "01",
                "status": "AVAILABLE",
                "observedAt": "2026-07-20T10:00:00+09:00",
            },
            {
                "stationId": "S1",
                "chargerId": "02",
                "status": "CHARGING",
                "observedAt": "2026-07-20T10:00:00+09:00",
            },
        ]
    )
    panel = build_gap_safe_panel(events, max_gap_minutes=25)
    ts = pd.Timestamp("2026-07-20T10:00:00+09:00")
    sub = panel[panel["panel_ts"] == ts]
    assert len(sub) == 2
    assert sub.duplicated(subset=["stationId", "chargerId"]).sum() == 0


def test_out_of_service_not_available():
    from gap_safe_panel import aggregate_station_features

    panel = _events(
        [
            {
                "panel_ts": "2026-07-20T10:00:00+09:00",
                "stationId": "S1",
                "chargerId": "01",
                "status": "OUT_OF_SERVICE",
                "segment_id": 0,
            },
            {
                "panel_ts": "2026-07-20T10:00:00+09:00",
                "stationId": "S1",
                "chargerId": "02",
                "status": "AVAILABLE",
                "segment_id": 0,
            },
        ]
    )
    panel["panel_ts"] = pd.to_datetime(panel["panel_ts"], utc=True).dt.tz_convert(
        "Asia/Seoul"
    )
    feat = aggregate_station_features(panel)
    row = feat.iloc[0]
    assert int(row["available_count"]) == 1
    assert float(row["out_of_service_ratio"]) == 0.5
