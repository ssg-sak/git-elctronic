"""Canonical paths for periodic collection loops (docs/data/loops/loop1..3).

Layout (by date):
  loop1/snapshots/YYYYMMDD/daegu_charger_status_YYYYMMDD_HHMMSS.csv
  loop3/YYYYMMDD/daegu_traffic_linkspeed_*.csv
  loop3/YYYYMMDD/daegu_traffic_incident_*.csv
  loop3/*_latest.csv  — always at loop3 root (pointer)
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LOOPS_ROOT = REPO / "docs" / "data" / "loops"
EXTRACTED_DIR = REPO / "docs" / "data" / "extracted"
LOOPS_ARCHIVE = LOOPS_ROOT / "_archive"

# extracted/ — one-shot domains (not live loops)
EXTRACTED_CHARGER_INFO = EXTRACTED_DIR / "charger" / "info"
EXTRACTED_CHARGER_STATUS = EXTRACTED_DIR / "charger" / "status"
EXTRACTED_CHARGER_USAGE = EXTRACTED_DIR / "charger" / "usage"
EXTRACTED_CHARGER_HOURS = EXTRACTED_DIR / "charger" / "hours"
EXTRACTED_TOUR = EXTRACTED_DIR / "tour"
EXTRACTED_PARKING = EXTRACTED_DIR / "parking"
EXTRACTED_TRAFFIC_ONESHOT = EXTRACTED_DIR / "traffic_oneshot"
EXTRACTED_TMAP = EXTRACTED_DIR / "tmap"
EXTRACTED_PROBES = EXTRACTED_DIR / "probes"
EXTRACTED_DAILY = EXTRACTED_DIR / "daily"

# loop1 — EvCharger status · alias: status
LOOP1_DIR = LOOPS_ROOT / "loop1"
LOOP1_SNAPSHOTS = LOOP1_DIR / "snapshots"
LOOP1_DAILY = LOOP1_DIR / "daily"
LOOP1_LOGS = LOOP1_DIR / "logs"
LOOP1_INDEX = LOOP1_DIR / "index.csv"

# loop2 — UTIC incident · alias: utic
LOOP2_DIR = LOOPS_ROOT / "loop2"

# loop3 — Daegu ITS linkspeed + dgincident · alias: daegu_traffic
LOOP3_DIR = LOOPS_ROOT / "loop3"

_LEGACY_SANDBOX_DATA = (
    REPO
    / "apps/data-pipeline/evaluation/personal/experiments"
    / "SANDBOX_20260717_status_periodic_collection/data"
)
_LEGACY_LOOP2 = LOOPS_ROOT / "utic"
_LEGACY_LOOP3 = LOOPS_ROOT / "daegu_traffic"

_YMD_IN_NAME = re.compile(r"_(\d{8})_")


def ymd_from_filename(name: str) -> str | None:
    """Extract YYYYMMDD from loop CSV names like …_20260725_083340.csv."""
    m = _YMD_IN_NAME.search(name)
    return m.group(1) if m else None


def loop1_day_dir(ymd: str) -> Path:
    return LOOP1_SNAPSHOTS / ymd


def loop3_day_dir(ymd: str) -> Path:
    return LOOP3_DIR / ymd


def iter_status_csvs(directory: Path) -> list[Path]:
    """Status CSVs in a snapshots root: flat and/or YYYYMMDD/ nested."""
    if not directory.is_dir():
        return []
    found: dict[str, Path] = {}
    for pattern in ("daegu_charger_status_*.csv", "*/daegu_charger_status_*.csv"):
        for fp in directory.glob(pattern):
            if not fp.is_file():
                continue
            prev = found.get(fp.name)
            if prev is None or len(fp.parts) >= len(prev.parts):
                found[fp.name] = fp
    return sorted(found.values(), key=lambda p: p.name)


def iter_loop3_csvs(
    root: Path | None = None,
    *,
    kind: str = "linkspeed",
) -> list[Path]:
    """Dated loop3 CSVs (excludes *_latest). kind: linkspeed | incident | all."""
    root = root or LOOP3_DIR
    if not root.is_dir():
        return []
    if kind == "linkspeed":
        patterns = [
            "daegu_traffic_linkspeed_*.csv",
            "*/daegu_traffic_linkspeed_*.csv",
        ]
    elif kind == "incident":
        patterns = [
            "daegu_traffic_incident_*.csv",
            "*/daegu_traffic_incident_*.csv",
        ]
    else:
        patterns = [
            "daegu_traffic_*.csv",
            "*/daegu_traffic_*.csv",
        ]
    found: dict[str, Path] = {}
    for pattern in patterns:
        for fp in root.glob(pattern):
            if not fp.is_file() or "latest" in fp.name:
                continue
            prev = found.get(fp.name)
            if prev is None or len(fp.parts) >= len(prev.parts):
                found[fp.name] = fp
    return sorted(found.values(), key=lambda p: p.name)


def status_data_dir() -> Path:
    if LOOP1_DIR.is_dir() and (LOOP1_SNAPSHOTS.exists() or LOOP1_INDEX.exists()):
        return LOOP1_DIR
    if _LEGACY_SANDBOX_DATA.is_dir():
        return _LEGACY_SANDBOX_DATA
    return LOOP1_DIR


def status_snapshots_dirs() -> list[Path]:
    """All snapshot roots to read (live loop1 + Lightsail archive + legacy)."""
    seen: set[Path] = set()
    dirs: list[Path] = []
    candidates: list[Path] = [LOOP1_SNAPSHOTS]
    if LOOPS_ARCHIVE.is_dir():
        candidates.extend(sorted(LOOPS_ARCHIVE.glob("from_lightsail_*/loop1/snapshots")))
    candidates.append(_LEGACY_SANDBOX_DATA / "snapshots")
    for candidate in candidates:
        if not candidate.is_dir():
            continue
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        dirs.append(candidate)
    return dirs or [LOOP1_SNAPSHOTS]


def status_snapshots_dir() -> Path:
    dirs = status_snapshots_dirs()
    return dirs[0]


def loop2_dir() -> Path:
    if LOOP2_DIR.is_dir():
        return LOOP2_DIR
    if _LEGACY_LOOP2.is_dir():
        return _LEGACY_LOOP2
    return LOOP2_DIR


def loop3_dir() -> Path:
    if LOOP3_DIR.is_dir():
        return LOOP3_DIR
    if _LEGACY_LOOP3.is_dir():
        return _LEGACY_LOOP3
    return LOOP3_DIR


def charger_info_csvs() -> list[Path]:
    """One-shot + daily charger info CSVs (newest last when sorted by caller)."""
    files = sorted(EXTRACTED_CHARGER_INFO.glob("daegu_charger_info_*.csv"))
    files += sorted(EXTRACTED_DAILY.glob("**/daegu_charger_info_*.csv"))
    return files


def charger_status_oneshot_csvs() -> list[Path]:
    return sorted(EXTRACTED_CHARGER_STATUS.glob("daegu_charger_status_*.csv"))


def parking_team5_csvs() -> list[Path]:
    return sorted(EXTRACTED_PARKING.glob("daegu_parking_*_team5*.csv"))


def parking_mock_csvs() -> list[Path]:
    """Deprecated: mock parking removed 2026-07-23. Kept as empty-safe alias."""
    return sorted(EXTRACTED_PARKING.glob("daegu_parking_*_mock.csv"))
