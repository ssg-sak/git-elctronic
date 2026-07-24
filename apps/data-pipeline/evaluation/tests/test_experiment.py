from __future__ import annotations

from pathlib import Path

import pytest

from csv_loader import load_extracted_dataset, merge_chargers, info_to_stations, load_charger_info_csv, load_charger_status_csv
from experiment import run_experiment


EXTRACTED = Path(__file__).resolve().parents[4] / "docs" / "data" / "extracted"


def test_merge_chargers_joins_status() -> None:
    info = load_charger_info_csv(
        EXTRACTED / "daegu_charger_info_20260717_194107.csv"
    ).head(5)
    status = load_charger_status_csv(
        EXTRACTED / "daegu_charger_status_20260717_194107.csv"
    ).head(5)
    merged = merge_chargers(info, status)
    assert "stat_updated_at" in merged.columns
    assert len(merged) == 5


@pytest.mark.skipif(not EXTRACTED.exists(), reason="extracted CSV 없음")
def test_run_experiment_on_real_csv() -> None:
    result = run_experiment(extracted_dir=EXTRACTED)
    assert result["input_counts"]["info_rows"] > 0
    assert result["processing_results"]["stations_after_cleansing"] > 0
    assert "reliability_grade_distribution" in result["processing_results"]
