from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

PROCESSING = Path(__file__).resolve().parents[2] / "processing"
if str(PROCESSING) not in sys.path:
    sys.path.insert(0, str(PROCESSING))

from vehicle.eta_soc_calculator_utils import EtaSocCalculator


@pytest.fixture(scope="module")
def calculator() -> EtaSocCalculator:
    return EtaSocCalculator()


def test_vehicle_master_has_unique_valid_models(calculator: EtaSocCalculator) -> None:
    master = calculator.df
    assert len(master) == 26
    assert master["model_name"].notna().all()
    assert not master["model_name"].duplicated().any()
    assert (master["battery_capacity_kwh"] > 0).all()
    assert (master["max_range_km"] > 0).all()


def test_registered_vehicle_uses_master(calculator: EtaSocCalculator) -> None:
    result = calculator.calculate_eta_soc("코나EV", 50, 50)
    assert result["used_fallback"] is False
    assert result["spec_source"] == "vehicle_master"
    assert result["battery_capacity_kwh"] == 64.0
    assert result["arrival_soc_percent"] == pytest.approx(37.68, abs=0.01)


def test_unknown_vehicle_uses_documented_conservative_fallback(
    calculator: EtaSocCalculator,
) -> None:
    result = calculator.calculate_eta_soc("등록되지 않은 차량", 50, 40)
    assert result["used_fallback"] is True
    assert result["battery_capacity_kwh"] == 50.0
    assert result["efficiency_km_per_kwh"] == 4.0
    assert result["arrival_soc_percent"] == 30.0


def test_zero_distance_preserves_soc(calculator: EtaSocCalculator) -> None:
    result = calculator.calculate_eta_soc("코나EV", 55, 0)
    assert result["consumed_kwh"] == 0
    assert result["arrival_soc_percent"] == 55


def test_more_distance_never_increases_arrival_soc(
    calculator: EtaSocCalculator,
) -> None:
    near = calculator.calculate_eta_soc("코나EV", 60, 10)
    far = calculator.calculate_eta_soc("코나EV", 60, 100)
    assert far["arrival_soc_percent"] < near["arrival_soc_percent"]


def test_danger_threshold_matches_soc_rule(calculator: EtaSocCalculator) -> None:
    boundary = calculator.calculate_eta_soc("코나EV", 10, 0)
    safe = calculator.calculate_eta_soc("코나EV", 10.1, 0)
    assert boundary["is_danger"] is True
    assert safe["is_danger"] is False


@pytest.mark.parametrize(
    ("current_soc", "distance_km"),
    [
        (-1, 10),
        (101, 10),
        (50, -1),
        (float("nan"), 10),
        (50, float("inf")),
    ],
)
def test_invalid_inputs_are_rejected(
    calculator: EtaSocCalculator,
    current_soc: float,
    distance_km: float,
) -> None:
    with pytest.raises(ValueError):
        calculator.calculate_eta_soc("코나EV", current_soc, distance_km)
