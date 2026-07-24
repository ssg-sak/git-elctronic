"""Unit tests for sandbox preprocessing (no network)."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from preprocessing.utils import normalize_str_series  # noqa: E402
from preprocessing.clean_weather import parse_precip_value  # noqa: E402
from preprocessing.clean_poi import _split_attr  # noqa: E402
from preprocessing.load_data import load_all  # noqa: E402
from preprocessing.paths import EXTRACTED_DIR, FILES  # noqa: E402


def test_extracted_files_exist():
    for fname in FILES.values():
        assert (EXTRACTED_DIR / fname).exists(), fname


def test_exclude_duplicate_name_pattern():
    assert "(1)" in "daegu_traffic_linkspeed_mock(1).csv"


def test_normalize_null_tokens():
    s = normalize_str_series(pd.Series(["  a  ", "", "null", "-", "None"]))
    assert s.isna().sum() == 4
    assert s.iloc[0] == "a"


def test_precip_parser():
    assert parse_precip_value("강수없음")[0] == 0.0
    assert parse_precip_value("적설없음")[0] == 0.0
    n, _, err = parse_precip_value("1mm 미만")
    assert not err and n == 1.0


def test_attr_split():
    name, val = _split_attr("이용시간|11:00~21:00")
    assert name == "이용시간"
    assert val.startswith("11:00")
    name2, val2 = _split_attr("주차시설|")
    assert name2 is not None and val2 is None


def test_load_all_smoke():
    data = load_all()
    assert "charger_info" in data
    assert len(data["charger_info"]) > 1000
    assert data["charger_status"]["chgerId"].dtype == "string" or str(
        data["charger_status"]["chgerId"].dtype
    ) == "string"
