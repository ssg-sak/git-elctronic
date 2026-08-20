"""Unit tests for F01–F03 station availability features."""
from __future__ import annotations

import pandas as pd

from station_features import (
    aggregate_availability_features,
    aggregate_observation_freshness,
    effective_grade,
    grade_from_age_minutes,
)


def test_f01_f02_f03_never_treat_unobserved_as_unavailable():
    df = pd.DataFrame(
        [
            {"statId": "S1", "stat_mapped": pd.NA, "status_missing": True},
            {"statId": "S1", "stat_mapped": "AVAILABLE", "status_missing": False},
            {"statId": "S1", "stat_mapped": "CHARGING", "status_missing": False},
            {"statId": "S1", "stat_mapped": "UNDER_INSPECTION", "status_missing": False},
        ]
    )
    out = aggregate_availability_features(df)
    row = out.iloc[0]
    assert row["total_chargers"] == 4
    assert row["unobserved_count"] == 1
    assert row["observed_count"] == 3
    assert row["available_count"] == 1
    assert abs(float(row["availability_ratio_observed"]) - 1 / 3) < 1e-9
    assert abs(float(row["unobserved_rate"]) - 0.25) < 1e-9
    assert bool(row["has_confirmed_available"]) is True


def test_f01_null_when_all_unobserved():
    df = pd.DataFrame(
        [
            {"statId": "S2", "stat_mapped": "UNKNOWN", "status_missing": True},
            {"statId": "S2", "stat_mapped": "UNKNOWN", "status_missing": True},
        ]
    )
    out = aggregate_availability_features(df)
    assert pd.isna(out.iloc[0]["availability_ratio_observed"])
    assert float(out.iloc[0]["unobserved_rate"]) == 1.0
    assert bool(out.iloc[0]["has_confirmed_available"]) is False


def test_reliability_grade_thresholds():
    assert grade_from_age_minutes(3) == "HIGH"
    assert grade_from_age_minutes(10) == "NORMAL"
    assert grade_from_age_minutes(20) == "CHECK_REQUIRED"
    assert grade_from_age_minutes(float("inf")) == "CHECK_REQUIRED"


def test_observation_state_separates_unobserved_from_stale():
    from station_features import observation_state

    obs = pd.Series([0, 2, 3, 1])
    grade = pd.Series(
        ["CHECK_REQUIRED", "CHECK_REQUIRED", "NORMAL", "HIGH"]
    )
    out = observation_state(obs, grade)
    assert list(out) == ["UNOBSERVED", "STALE", "NORMAL", "FRESH"]


def test_observation_freshness_station_min():
    df = pd.DataFrame(
        [
            {
                "statId": "S1",
                "stat_mapped": "AVAILABLE",
                "status_missing": False,
                "status_age_seconds": 3600.0,
                "observation_age_seconds": 900.0,
            },
            {
                "statId": "S1",
                "stat_mapped": "CHARGING",
                "status_missing": False,
                "status_age_seconds": 1800.0,
                "observation_age_seconds": 600.0,
            },
        ]
    )
    out = aggregate_observation_freshness(df)
    row = out.iloc[0]
    assert abs(float(row["observation_age_minutes"]) - 10.0) < 1e-9
    assert row["observation_grade"] == "NORMAL"
    assert row["reliability_grade_effective"] == "NORMAL"
