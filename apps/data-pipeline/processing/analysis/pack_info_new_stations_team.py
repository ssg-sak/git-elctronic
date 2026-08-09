"""Deprecated path — use processing/tools/share/pack_info_new_stations_team.py

Run:
  python apps/data-pipeline/processing/tools/share/pack_info_new_stations_team.py
"""
from __future__ import annotations

import runpy
from pathlib import Path

_TARGET = Path(__file__).resolve().parents[1] / "tools" / "share" / "pack_info_new_stations_team.py"

if __name__ == "__main__":
    runpy.run_path(str(_TARGET), run_name="__main__")
