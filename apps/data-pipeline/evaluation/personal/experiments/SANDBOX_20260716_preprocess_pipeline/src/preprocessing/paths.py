"""Sandbox paths and file manifest. Raw CSVs stay in docs/data/extracted (read-only)."""
from __future__ import annotations

from pathlib import Path

SANDBOX_ROOT = Path(__file__).resolve().parents[2]
# parents: preprocessing -> src -> SANDBOX
REPO_ROOT = SANDBOX_ROOT.parents[5]  # -> git-elctronic

EXTRACTED_DIR = REPO_ROOT / "docs" / "data" / "extracted"
RAW_DIR = SANDBOX_ROOT / "data" / "raw"
INTERIM_DIR = SANDBOX_ROOT / "data" / "interim"
PROCESSED_DIR = SANDBOX_ROOT / "data" / "processed"
QUARANTINE_DIR = SANDBOX_ROOT / "data" / "quarantine"
REPORT_DIR = SANDBOX_ROOT / "reports" / "data_quality"
CONFIG_DIR = Path(__file__).resolve().parent / "config"

EXCLUDE_NAME_SUBSTRINGS = ["(1)"]


def _latest_csv(prefix: str, *, require_cols: tuple[str, ...] = ()) -> str:
    """docs/data/extracted (및 도메인 하위폴더)에서 prefix 기준 최신 CSV의 상대 경로."""
    import pandas as pd

    matches = [
        p
        for p in EXTRACTED_DIR.rglob(f"{prefix}*.csv")
        if not any(tok in p.name for tok in EXCLUDE_NAME_SUBSTRINGS)
        and "quarantine" not in p.name.lower()
    ]
    if not matches:
        raise FileNotFoundError(f"No CSV matching {prefix}*.csv under {EXTRACTED_DIR}")
    if require_cols:
        ok = []
        for p in matches:
            try:
                cols = set(pd.read_csv(p, nrows=0).columns)
            except Exception:
                continue
            if all(c in cols for c in require_cols):
                ok.append(p)
        if ok:
            matches = ok
    latest = max(matches, key=lambda p: p.stat().st_mtime)
    return latest.relative_to(EXTRACTED_DIR).as_posix()


FILES = {
    # daily slim exports may omit limitYn — require it for access filter / D1
    "charger_info": _latest_csv("daegu_charger_info_", require_cols=("limitYn",)),
    "charger_status": _latest_csv("daegu_charger_status_"),
    "city_tour": _latest_csv("daegu_city_tour_"),
    "parking_info": "parking/daegu_parking_info_team5_latest.csv",
    "parking_realtime": "parking/daegu_parking_realtime_team5_latest.csv",
    "tour_attractions": _latest_csv("daegu_tour_attractions_"),
    "walk_parks": _latest_csv("daegu_walk_parks_"),
}

STRING_ID_COLS = {
    "statId", "chgerId", "chgerType", "stat", "pkltId", "incidentId",
    "affectLinkId", "linkId", "startNodeId", "endNodeId", "category",
    "baseDate", "baseTime", "fcstDate", "fcstTime", "nx", "ny", "contentid",
    "mngNo", "sysgrpyYn", "useYn", "delYn", "limitYn", "parkingFree",
}

DAEGU_LAT_MIN, DAEGU_LAT_MAX = 35.55, 36.45
DAEGU_LNG_MIN, DAEGU_LNG_MAX = 128.25, 129.05

STATUS_STALE_SECONDS = 15 * 60
