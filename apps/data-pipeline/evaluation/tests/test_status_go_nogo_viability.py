"""Deprecated path — use evaluation/viability_tests/ instead."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

TARGET = (
    Path(__file__).resolve().parents[1]
    / "viability_tests"
    / "test_status_go_nogo_viability.py"
)

if __name__ == "__main__":
    print(f"[redirect] → {TARGET}", flush=True)
    raise SystemExit(subprocess.call([sys.executable, str(TARGET)], cwd=str(Path(__file__).resolve().parents[4])))
