"""Deprecated path — use processing/tools/share/probe_info_coverage_gaps.py

Run:
  python apps/data-pipeline/processing/tools/share/probe_info_coverage_gaps.py
"""
from __future__ import annotations

import runpy
from pathlib import Path

_TARGET = Path(__file__).resolve().parents[1] / "tools" / "share" / "probe_info_coverage_gaps.py"

if __name__ == "__main__":
    runpy.run_path(str(_TARGET), run_name="__main__")
