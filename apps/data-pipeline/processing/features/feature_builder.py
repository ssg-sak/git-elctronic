"""Station features aligned with DATA_PART_WORK_GUIDE §4.6."""
from __future__ import annotations

import pandas as pd

import sys
from pathlib import Path
_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))
from _bootstrap import ensure_paths

ensure_paths()

from features.gap_safe_panel import aggregate_station_features


def add_station_features(panel: pd.DataFrame) -> pd.DataFrame:
    """Alias for guide example — delegates to aggregate_station_features."""
    return aggregate_station_features(panel)
