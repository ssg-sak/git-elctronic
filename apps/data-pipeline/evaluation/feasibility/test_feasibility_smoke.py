"""Smoke tests for feasibility helpers."""
from __future__ import annotations

import sys
from pathlib import Path

EVAL = Path(__file__).resolve().parents[1]
if str(EVAL) not in sys.path:
    sys.path.insert(0, str(EVAL))


def test_primary_horizon_is_15():
    from feasibility.eta_targets import PRIMARY

    assert PRIMARY == 15


def test_ensure_out_creates_dirs():
    from feasibility.paths import OUT_FIGURES, OUT_ROOT, OUT_TABLES, ensure_out

    ensure_out()
    assert OUT_ROOT.is_dir()
    assert OUT_TABLES.is_dir()
    assert OUT_FIGURES.is_dir()


def test_verdict_labels():
    from feasibility.verdict import run_verdict

    v = run_verdict(
        {
            "status_quality": {"n_snapshots": 1, "gap_distribution": {"median_min": 10, "pct_le_5_5min": 0.1}},
            "panel_restore": {"ok": True, "impossible": False, "observed_rate": 0.1, "impute_rate": 0.1, "null_rate": 0.8},
            "eta_targets": {
                "eta15": {"labeled_rows": 100, "coverage": 0.05, "dates_with_label": 3, "positive_rate": 0.7},
                "temporal_split_feasible": True,
            },
            "usage_eda": {"ok": True, "rows": 1, "rows_2025": 1, "role_verdict": "aux"},
            "backtest": {"skipped": True, "ok": False, "reason": "too few"},
        }
    )
    assert v["grade_label"] in {"GO", "CONDITIONAL GO", "NO-GO"}
    assert v["grade"] == "B_CONDITIONAL_GO"
