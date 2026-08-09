"""pytest 공통 설정 — processing 모듈 경로 등록."""
from __future__ import annotations

import sys
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent.parent
PROCESSING_DIR = EVAL_DIR.parent / "processing"
FIXTURES_DIR = EVAL_DIR / "fixtures"

# Flat imports in tests (from gap_safe_panel import ...) live under subpackages.
for _p in (
    PROCESSING_DIR,
    PROCESSING_DIR / "features",
    PROCESSING_DIR / "core",
    PROCESSING_DIR / "analysis",
    EVAL_DIR,
):
    if _p.is_dir() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
