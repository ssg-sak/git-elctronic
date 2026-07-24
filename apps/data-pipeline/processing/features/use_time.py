"""F08: parse EvCharger `useTime` → is_operating_now (Y/N/UNKNOWN).

Policy (docs/data/스키마/피처_카탈로그.md):
- missing / unparseable → UNKNOWN (never assume 24h)
- 24h phrases → Y
- weekday/weekend splits when hours are clear
- public holidays: treated like weekend when the text groups them; no holiday calendar

Does not score stations (AI·data ②).
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

import pandas as pd

OperatingStatus = Literal["Y", "N", "UNKNOWN"]

KST = ZoneInfo("Asia/Seoul")

_ALWAYS_CLOSED = re.compile(
    r"^\(?\s*(비개방|미개방|개방불가)\s*\)?$|"
    r"^(비개방|미개방)(\s|$|\(|:)|"
    r"주중/주말\s*:\s*개방불가|"
    r"비개방\s*\(|"
    r"업무시설\s*미개방"
)

_ALWAYS_OPEN = re.compile(
    r"24\s*시간|종일|"
    r"\(24\s*시\)|"  # e.g. 비공용충전기(24시)
    r"00\s*:\s*00\s*[~\-–—～]\s*23\s*:\s*59|"
    r"00\s*:\s*00\s*[~\-–—～]\s*24\s*:\s*00|"
    r"주중/주말\s*:\s*24"
)

# 05:00~익일01:00
_RANGE_NEXT_DAY = re.compile(
    r"(?<!\d)(\d{1,2})\s*[:：]\s*(\d{2})\s*[~\-–—～]\s*익일\s*(\d{1,2})\s*[:：]\s*(\d{2})"
)

# Weekend (and often 공휴일) closed — use weekday hours on Mon–Fri only
_WEEKEND_CLOSED = re.compile(
    r"(주말|토\s*,?\s*일|토일).{0,12}(미개방|이용불가|휴무|제외)|"
    r"(공휴일).{0,8}(미개방|이용불가|휴무|제외)|"
    r"주말\s*\(?\s*공휴일\s*\)?\s*미개방|"
    r"토\s*,\s*일\s*,\s*공휴일\s*이용불가"
)

# HH:MM ~ HH:MM (optional seconds)
_RANGE_HM = re.compile(
    r"(?<!\d)(\d{1,2})\s*[:：]\s*(\d{2})(?:\s*[:：]\s*\d{2})?"
    r"\s*[~\-–—～]\s*"
    r"(\d{1,2})\s*[:：]\s*(\d{2})(?:\s*[:：]\s*\d{2})?"
)

# 09시~23시 / 9시 ~ 18시
_RANGE_SI = re.compile(
    r"(?<!\d)(\d{1,2})\s*시\s*[~\-–—～]\s*(\d{1,2})\s*시"
)

# 9-22시 / 8~18시 (hour only, trailing 시 optional on end)
_RANGE_H_ONLY = re.compile(
    r"(?<!\d)(\d{1,2})\s*[~\-–—～]\s*(\d{1,2})\s*시"
)

_WEEKDAY_MARK = re.compile(r"평일|주중")
_WEEKEND_MARK = re.compile(r"주말|토\s*,?\s*일|공휴일|토요일")


def _to_minutes(hour: int, minute: int = 0) -> int | None:
    if hour == 24 and minute == 0:
        return 24 * 60
    if hour < 0 or hour > 24 or minute < 0 or minute > 59:
        return None
    if hour == 24:
        return None
    return hour * 60 + minute


def _in_range(now_m: int, start_m: int, end_m: int) -> bool:
    """Inclusive start, exclusive end. Overnight if start > end."""
    if start_m == end_m:
        return False
    if start_m < end_m:
        return start_m <= now_m < end_m
    # overnight e.g. 19:00~08:00
    return now_m >= start_m or now_m < end_m


def _extract_ranges(text: str) -> list[tuple[int, int]]:
    found: list[tuple[int, int]] = []
    for m in _RANGE_NEXT_DAY.finditer(text):
        s = _to_minutes(int(m.group(1)), int(m.group(2)))
        e = _to_minutes(int(m.group(3)), int(m.group(4)))
        if s is not None and e is not None:
            found.append((s, e))
    for m in _RANGE_HM.finditer(text):
        s = _to_minutes(int(m.group(1)), int(m.group(2)))
        e = _to_minutes(int(m.group(3)), int(m.group(4)))
        if s is not None and e is not None:
            found.append((s, e))
    for m in _RANGE_SI.finditer(text):
        s = _to_minutes(int(m.group(1)), 0)
        e = _to_minutes(int(m.group(2)), 0)
        if s is not None and e is not None:
            found.append((s, e))
    # hour-only only if no HH:MM found yet (avoid double-hit on "09:00~18:00")
    if not found:
        for m in _RANGE_H_ONLY.finditer(text):
            s = _to_minutes(int(m.group(1)), 0)
            e = _to_minutes(int(m.group(2)), 0)
            if s is not None and e is not None:
                found.append((s, e))
    return found


def _split_weekday_weekend_clauses(text: str) -> tuple[str | None, str | None]:
    """Best-effort split into weekday vs weekend clause strings."""
    # Normalize separators
    t = re.sub(r"[／/]", ",", text)
    parts = re.split(r"[,，]", t)
    wd_parts: list[str] = []
    we_parts: list[str] = []
    other: list[str] = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        has_wd = bool(_WEEKDAY_MARK.search(p))
        has_we = bool(_WEEKEND_MARK.search(p))
        if has_wd and not has_we:
            wd_parts.append(p)
        elif has_we and not has_wd:
            we_parts.append(p)
        elif has_wd and has_we:
            # e.g. 주중/주말 : 06시~23시 — same hours both
            other.append(p)
        else:
            other.append(p)
    wd = " ".join(wd_parts) if wd_parts else None
    we = " ".join(we_parts) if we_parts else None
    if wd is None and we is None and other:
        # single clause shared
        joined = " ".join(other)
        if _WEEKDAY_MARK.search(joined) or _WEEKEND_MARK.search(joined):
            return joined, joined
        return joined, joined
    if wd is None and other and _WEEKDAY_MARK.search(text):
        wd = " ".join(other)
    return wd, we


def is_operating_now(
    use_time: str | float | None,
    when: datetime | None = None,
) -> OperatingStatus:
    """Return Y / N / UNKNOWN for whether the station is open at `when` (KST)."""
    if use_time is None or (isinstance(use_time, float) and pd.isna(use_time)):
        return "UNKNOWN"
    text = str(use_time).strip()
    if not text or text.lower() in {"nan", "none", "null"} or text in {"~", "-"}:
        return "UNKNOWN"

    if when is None:
        when = datetime.now(KST)
    elif when.tzinfo is None:
        when = when.replace(tzinfo=KST)
    else:
        when = when.astimezone(KST)

    now_m = when.hour * 60 + when.minute
    is_weekend = when.weekday() >= 5  # Sat/Sun; 공휴일 calendar not applied

    # Always closed (before 24h — "비개방" wins)
    if _ALWAYS_CLOSED.search(text) and not _extract_ranges(text):
        return "N"
    if re.search(r"개방불가", text) and not _extract_ranges(text):
        return "N"

    # 24h open (time-wise; access restrictions ignored)
    if _ALWAYS_OPEN.search(text):
        return "Y"

    # Vague store hours — no clock → UNKNOWN
    if re.search(r"매장\s*(영업|운영)\s*시간|운영시간\s*이용|시설\s*운영\s*시간", text):
        if not _extract_ranges(text):
            return "UNKNOWN"

    # Weekend closed policy
    if _WEEKEND_CLOSED.search(text) and is_weekend:
        return "N"

    ranges_all = _extract_ranges(text)
    if not ranges_all:
        return "UNKNOWN"

    has_day_marks = bool(_WEEKDAY_MARK.search(text) or _WEEKEND_MARK.search(text))

    if has_day_marks:
        wd_clause, we_clause = _split_weekday_weekend_clauses(text)
        if is_weekend:
            if _WEEKEND_CLOSED.search(text):
                return "N"
            clause = we_clause or text
            # "주중/주말 : 06시~23시" → shared
            if wd_clause and we_clause is None and "주중/주말" in text.replace(" ", ""):
                clause = text
            ranges = _extract_ranges(clause) or ranges_all
        else:
            clause = wd_clause or text
            ranges = _extract_ranges(clause) or ranges_all

        if not ranges:
            return "UNKNOWN"
        # If multiple ranges in the applicable clause, require any match (rare)
        if any(_in_range(now_m, s, e) for s, e in ranges):
            return "Y"
        return "N"

    # No day-of-week marks: single (or repeated) clock range
    # Prefer first range; if all identical use that; if conflicting → UNKNOWN
    uniq = list(dict.fromkeys(ranges_all))
    if len(uniq) == 1:
        s, e = uniq[0]
        return "Y" if _in_range(now_m, s, e) else "N"
    if len(uniq) == 2 and abs(uniq[0][0] - uniq[1][0]) < 60:
        # e.g. weekday vs weekend hours without clear labels — ambiguous
        return "UNKNOWN"
    # Multiple different unlabeled ranges → UNKNOWN
    return "UNKNOWN"


def series_is_operating_now(
    use_times: pd.Series,
    when: datetime | None = None,
) -> pd.Series:
    """Vectorized wrapper → Series of Y/N/UNKNOWN."""
    when = when or datetime.now(KST)
    return use_times.map(lambda x: is_operating_now(x, when))
