"""CLI entry: python apps/data-pipeline/evaluation/feasibility/run_all.py"""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

EVAL = Path(__file__).resolve().parent.parent
if str(EVAL) not in sys.path:
    sys.path.insert(0, str(EVAL))

if __name__ == "__main__":
    # Import package-relative main
    from feasibility.run_all import main

    raise SystemExit(main())
