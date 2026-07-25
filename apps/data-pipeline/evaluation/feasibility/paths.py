"""Paths for timeseries feasibility gate (read-only over source data)."""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVAL = HERE.parent
DATA_PIPELINE = EVAL.parent
REPO = DATA_PIPELINE.parent.parent  # .../apps/data-pipeline -> repo root

if str(DATA_PIPELINE) not in sys.path:
    sys.path.insert(0, str(DATA_PIPELINE))

from loop_paths import (  # noqa: E402
    EXTRACTED_CHARGER_USAGE,
    EXTRACTED_DIR,
    LOOP1_DIR,
    LOOP1_INDEX,
    LOOP1_LOGS,
    LOOP1_SNAPSHOTS,
    charger_info_csvs,
    charger_status_oneshot_csvs,
    iter_status_csvs,
    parking_team5_csvs,
    status_snapshots_dirs,
)

OUT_ROOT = DATA_PIPELINE / "reports" / "timeseries_feasibility"
OUT_TABLES = OUT_ROOT / "tables"
OUT_FIGURES = OUT_ROOT / "figures"
OUT_JSON = OUT_ROOT / "json"
EXP_DIR = EVAL / "personal" / "experiments"

USAGE_CSV = EXTRACTED_CHARGER_USAGE / "daegu_charger_usage_daily_20260331.csv"
USAGE_JOIN = REPO / "docs" / "data" / "spatial_join" / "join_usage_history_statId.csv"
HISTORY_FEAT = EVAL / "results" / "datasets" / "station_history_features_latest.csv"
CALL_LOG = LOOP1_LOGS / "call_log.jsonl"
D1_LATEST = EVAL / "results" / "datasets" / "station_feature_snapshot_latest.csv"


def ensure_out() -> None:
    for p in (OUT_ROOT, OUT_TABLES, OUT_FIGURES, OUT_JSON):
        p.mkdir(parents=True, exist_ok=True)
