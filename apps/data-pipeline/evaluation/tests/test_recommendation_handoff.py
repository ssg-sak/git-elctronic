from __future__ import annotations

import sys
from pathlib import Path

ANALYSIS = Path(__file__).resolve().parents[2] / "processing" / "analysis"
if str(ANALYSIS) not in sys.path:
    sys.path.insert(0, str(ANALYSIS))

from build_recommendation_handoff import freshness_flag


def test_freshness_boundaries() -> None:
    assert freshness_flag(None) == "UNOBSERVED"
    assert freshness_flag(5) == "FRESH"
    assert freshness_flag(5.01) == "AGING"
    assert freshness_flag(15) == "AGING"
    assert freshness_flag(15.01) == "CHECK_REQUIRED"
