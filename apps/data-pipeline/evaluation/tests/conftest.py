"""pytest 공통 설정 — processing 모듈 경로 등록."""
from __future__ import annotations

import sys
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent.parent
PROCESSING_DIR = EVAL_DIR.parent / "processing"
FIXTURES_DIR = EVAL_DIR / "fixtures"

sys.path.insert(0, str(PROCESSING_DIR))
sys.path.insert(0, str(EVAL_DIR))
