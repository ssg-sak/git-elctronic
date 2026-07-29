from __future__ import annotations

import sys
from pathlib import Path

PROCESSING_ANALYSIS = Path(__file__).resolve().parents[2] / "processing" / "analysis"
if str(PROCESSING_ANALYSIS) not in sys.path:
    sys.path.insert(0, str(PROCESSING_ANALYSIS))

from monitor_recommendation_input_quality import classify_report


def report_with(*, duplicate_rate: float, conflicts: int, curated_status: str = "PASS") -> dict:
    return {
        "recommendation_ready": True,
        "source_root": "docs/data/loops/loop1/snapshots",
        "profile": {
            "cadence_p95_minutes": 15.0,
            "latest_local_age_minutes": 10.0,
        },
        "checks": [
            {
                "code": "RAW_GRAIN_UNIQUENESS",
                "status": "WARN" if duplicate_rate else "PASS",
                "evidence": {
                    "duplicate_rate": duplicate_rate,
                    "conflicting_status_groups": conflicts,
                },
            },
            {"code": "CURATED_GRAIN_UNIQUENESS", "status": curated_status},
        ],
        "summary": {"PASS": 6, "WARN": 1, "FAIL": 0},
    }


def test_current_baseline_is_observation_warn_only() -> None:
    result = classify_report(report_with(duplicate_rate=0.002062, conflicts=6))

    assert result["monitor_status"] == "PASS"
    assert result["recommendation_ready"] is True


def test_material_duplicate_spike_is_fail() -> None:
    result = classify_report(report_with(duplicate_rate=0.025, conflicts=6))

    assert result["monitor_status"] == "FAIL"
    assert result["recommendation_ready"] is False


def test_curated_duplicate_blocks_handoff() -> None:
    result = classify_report(
        report_with(duplicate_rate=0.002, conflicts=6, curated_status="FAIL")
    )

    assert result["monitor_status"] == "FAIL"
    assert result["recommendation_ready"] is False
