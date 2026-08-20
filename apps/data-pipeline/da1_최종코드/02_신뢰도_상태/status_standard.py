"""Official API status codes (DATA_PART_WORK_GUIDE §4.2).

Internal pipeline may use finer codes (OUT_OF_ORDER, UNDER_INSPECTION).
"""
from __future__ import annotations

OFFICIAL_STATUSES = frozenset({"AVAILABLE", "CHARGING", "OUT_OF_SERVICE", "UNKNOWN"})

RAW_TO_OFFICIAL: dict[str, str] = {
    "1": "OUT_OF_SERVICE",
    "01": "OUT_OF_SERVICE",
    "2": "AVAILABLE",
    "02": "AVAILABLE",
    "3": "CHARGING",
    "03": "CHARGING",
    "4": "OUT_OF_SERVICE",
    "04": "OUT_OF_SERVICE",
    "5": "OUT_OF_SERVICE",
    "05": "OUT_OF_SERVICE",
    "9": "UNKNOWN",
    "09": "UNKNOWN",
}

INTERNAL_TO_OFFICIAL: dict[str, str] = {
    "AVAILABLE": "AVAILABLE",
    "CHARGING": "CHARGING",
    "IN_USE": "CHARGING",
    "OUT_OF_ORDER": "OUT_OF_SERVICE",
    "UNDER_INSPECTION": "OUT_OF_SERVICE",
    "UNKNOWN": "UNKNOWN",
    "STATUS_UNKNOWN": "UNKNOWN",
}


def map_raw_stat(raw: str | int | None) -> str:
    if raw is None:
        return "UNKNOWN"
    key = str(raw).strip()
    if not key:
        return "UNKNOWN"
    return RAW_TO_OFFICIAL.get(key, RAW_TO_OFFICIAL.get(key.zfill(2), "UNKNOWN"))


def to_official_status(status: str | None) -> str:
    if status is None:
        return "UNKNOWN"
    s = str(status).strip().upper()
    if s in OFFICIAL_STATUSES:
        return s
    return INTERNAL_TO_OFFICIAL.get(s, "UNKNOWN")
