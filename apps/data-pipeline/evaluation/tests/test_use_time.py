"""Unit tests for F08 useTime → is_operating_now."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from use_time import is_operating_now

KST = ZoneInfo("Asia/Seoul")


def _dt(y, m, d, hh, mm, weekday_hint: str | None = None) -> datetime:
    """weekday_hint unused — date must match intended weekday."""
    return datetime(y, m, d, hh, mm, tzinfo=KST)


# 2026-07-20 = Monday, 2026-07-25 = Saturday


def test_missing_is_unknown():
    assert is_operating_now(None, _dt(2026, 7, 20, 12, 0)) == "UNKNOWN"
    assert is_operating_now("", _dt(2026, 7, 20, 12, 0)) == "UNKNOWN"
    assert is_operating_now("~", _dt(2026, 7, 20, 12, 0)) == "UNKNOWN"


def test_24h_is_y():
    noon = _dt(2026, 7, 20, 12, 0)
    night = _dt(2026, 7, 20, 3, 0)
    for text in (
        "24시간 이용가능",
        "24시간",
        "00:00 ~ 23:59",
        "00:00~24:00",
        "주중/주말 : 24시간",
        "24시간 이용가능,입주민만 사용가능 거주자외출입제한",
    ):
        assert is_operating_now(text, noon) == "Y", text
        assert is_operating_now(text, night) == "Y", text


def test_simple_range_weekday():
    open_t = _dt(2026, 7, 20, 10, 0)  # Mon
    closed_t = _dt(2026, 7, 20, 19, 0)
    assert is_operating_now("09:00~18:00", open_t) == "Y"
    assert is_operating_now("09:00~18:00", closed_t) == "N"
    assert is_operating_now("09시~23시", _dt(2026, 7, 20, 22, 0)) == "Y"
    assert is_operating_now("09시~23시", _dt(2026, 7, 20, 23, 30)) == "N"


def test_overnight():
    fri_night = _dt(2026, 7, 20, 20, 0)  # Mon 20:00 still overnight window for 19~08
    early = _dt(2026, 7, 20, 7, 0)
    midday = _dt(2026, 7, 20, 12, 0)
    assert is_operating_now("19:00~08:00", fri_night) == "Y"
    assert is_operating_now("19:00~08:00", early) == "Y"
    assert is_operating_now("19:00~08:00", midday) == "N"


def test_weekend_closed():
    sat = _dt(2026, 7, 25, 12, 0)  # Sat
    mon = _dt(2026, 7, 20, 12, 0)
    text = "평일 09:00~18:00, 주말 및 공휴일 미개방"
    assert is_operating_now(text, sat) == "N"
    assert is_operating_now(text, mon) == "Y"
    assert is_operating_now(text, _dt(2026, 7, 20, 19, 0)) == "N"


def test_weekday_weekend_split_hours():
    mon = _dt(2026, 7, 20, 18, 30)
    sat = _dt(2026, 7, 25, 18, 30)
    text = "주중 08:00~19:00, 주말 09:00~18:00"
    assert is_operating_now(text, mon) == "Y"  # before 19
    assert is_operating_now(text, sat) == "N"  # after 18
    assert is_operating_now(text, _dt(2026, 7, 25, 10, 0)) == "Y"


def test_always_closed():
    noon = _dt(2026, 7, 20, 12, 0)
    assert is_operating_now("비개방", noon) == "N"
    assert is_operating_now("미개방", noon) == "N"


def test_vague_store_hours_unknown():
    noon = _dt(2026, 7, 20, 12, 0)
    assert is_operating_now("매장영업시간", noon) == "UNKNOWN"
    assert is_operating_now("시설 운영 시간", noon) == "UNKNOWN"


def test_shared_weekday_weekend_hours():
    text = "주중/주말 : 06시~23시"
    assert is_operating_now(text, _dt(2026, 7, 20, 7, 0)) == "Y"
    assert is_operating_now(text, _dt(2026, 7, 25, 7, 0)) == "Y"
    assert is_operating_now(text, _dt(2026, 7, 20, 23, 30)) == "N"


def test_paren_closed_and_24si():
    noon = _dt(2026, 7, 20, 12, 0)
    assert is_operating_now("(비개방)", noon) == "N"
    assert is_operating_now("비공용충전기(24시)", noon) == "Y"


def test_next_day_range():
    assert is_operating_now("05:00~익일01:00", _dt(2026, 7, 20, 22, 0)) == "Y"
    assert is_operating_now("05:00~익일01:00", _dt(2026, 7, 20, 2, 0)) == "N"
