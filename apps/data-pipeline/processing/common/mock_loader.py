"""Load official mock JSON inputs (DATA_PART_WORK_GUIDE §4.3)."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

REPO_import sys
from pathlib import Path
_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))
from _bootstrap import ensure_paths

ROOT = ensure_paths()
JSON_DIR = REPO_ROOT / "json"
HISTORY_PATH = JSON_DIR / "charger-status-history.json"
STATIONS_PATH = JSON_DIR / "stations.json"


def load_charger_history(path: str | Path | None = None) -> pd.DataFrame:
    fp = Path(path) if path else HISTORY_PATH
    records = json.loads(fp.read_text(encoding="utf-8"))
    df = pd.DataFrame(records)
    for col in ("observedAt", "statusUpdatedAt"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], utc=True).dt.tz_convert("Asia/Seoul")
    return df


def load_stations(path: str | Path | None = None) -> pd.DataFrame:
    fp = Path(path) if path else STATIONS_PATH
    records = json.loads(fp.read_text(encoding="utf-8"))
    return pd.DataFrame(records)
