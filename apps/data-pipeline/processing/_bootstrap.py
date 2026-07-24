"""Put `processing/` and `apps/data-pipeline/` on sys.path for script entrypoints."""
from __future__ import annotations

import sys
from pathlib import Path

PROCESSING = Path(__file__).resolve().parent
DATA_PIPELINE = PROCESSING.parent
REPO = DATA_PIPELINE.parent.parent


def ensure_paths() -> Path:
    for p in (str(PROCESSING), str(DATA_PIPELINE)):
        if p not in sys.path:
            sys.path.insert(0, p)
    return REPO
