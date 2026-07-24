from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

import cleansing

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


@pytest.fixture
def stations_sample() -> pd.DataFrame:
    return pd.read_csv(FIXTURES / "stations_sample.csv", dtype=str)


@pytest.fixture
def chargers_sample() -> pd.DataFrame:
    return pd.read_csv(FIXTURES / "chargers_sample.csv", dtype=str)


def test_clean_stations_drops_invalid_coords(stations_sample: pd.DataFrame) -> None:
    cleaned = cleansing.clean_stations(stations_sample)
    assert len(cleaned) == 1
    assert cleaned.iloc[0]["stat_id"] == "ST001"


def test_clean_stations_drops_missing_addr(stations_sample: pd.DataFrame) -> None:
    cleaned = cleansing.clean_stations(stations_sample)
    assert "ST003" not in set(cleaned["stat_id"])


def test_clean_chargers_maps_type_and_stat(chargers_sample: pd.DataFrame) -> None:
    cleaned = cleansing.clean_chargers(chargers_sample)
    row = cleaned[cleaned["chger_id"] == "01"].iloc[0]
    assert row["chger_type"] == "DC콤보"
    assert row["stat"] == "AVAILABLE"
