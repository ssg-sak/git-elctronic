"""Monitor DA① recommendation-input quality and collection freshness.

This is intentionally separate from the validator: the validator reports the
current dataset facts, while this module applies operational thresholds so a
daily run can be classified as PASS, WARN, or FAIL.

Usage:
  python apps/data-pipeline/processing/analysis/monitor_recommendation_input_quality.py
  python .../monitor_recommendation_input_quality.py --history path/to/history.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))

from _bootstrap import ensure_paths

REPO = ensure_paths()
KST = ZoneInfo("Asia/Seoul")
DEFAULT_OUTPUT = REPO / "docs" / "data" / "quality" / "recommendation_input_monitor_latest.json"

# These thresholds are intentionally above the current baseline (0.2062% raw
# duplicate rate, 15.02-minute cadence p95) to detect a material regression.
RAW_DUPLICATE_WARN_RATE = 0.005
RAW_DUPLICATE_FAIL_RATE = 0.02
CONFLICT_GROUP_WARN = 20
CONFLICT_GROUP_FAIL = 100
CADENCE_P95_WARN_MINUTES = 20.0
CADENCE_P95_FAIL_MINUTES = 30.0
LATEST_AGE_WARN_MINUTES = 60.0
LATEST_AGE_FAIL_MINUTES = 180.0


def _level(value: float | int | None, warn: float, fail: float) -> str:
    if value is None:
        return "FAIL"
    if value >= fail:
        return "FAIL"
    if value >= warn:
        return "WARN"
    return "PASS"


def classify_report(report: dict[str, Any]) -> dict[str, Any]:
    """Apply monitoring thresholds to an existing validator report."""
    profile = report.get("profile", {})
    checks = {item["code"]: item for item in report.get("checks", [])}
    raw = checks.get("RAW_GRAIN_UNIQUENESS", {}).get("evidence", {})
    duplicate_rate = raw.get("duplicate_rate")
    conflict_groups = raw.get("conflicting_status_groups")
    cadence_p95 = profile.get("cadence_p95_minutes")
    latest_age = profile.get("latest_local_age_minutes")

    metrics = [
        {
            "code": "RAW_DUPLICATE_RATE",
            "status": _level(duplicate_rate, RAW_DUPLICATE_WARN_RATE, RAW_DUPLICATE_FAIL_RATE),
            "value": duplicate_rate,
            "warn_at": RAW_DUPLICATE_WARN_RATE,
            "fail_at": RAW_DUPLICATE_FAIL_RATE,
            "policy": "raw duplicate is retained; curated grain must still be unique",
        },
        {
            "code": "CONFLICTING_STATUS_GROUPS",
            "status": _level(conflict_groups, CONFLICT_GROUP_WARN, CONFLICT_GROUP_FAIL),
            "value": conflict_groups,
            "warn_at": CONFLICT_GROUP_WARN,
            "fail_at": CONFLICT_GROUP_FAIL,
            "policy": "inspect page-boundary conflicts and keep latest statUpdDt",
        },
        {
            "code": "CADENCE_P95_MINUTES",
            "status": _level(cadence_p95, CADENCE_P95_WARN_MINUTES, CADENCE_P95_FAIL_MINUTES),
            "value": cadence_p95,
            "warn_at": CADENCE_P95_WARN_MINUTES,
            "fail_at": CADENCE_P95_FAIL_MINUTES,
            "policy": "collection gaps reduce temporal coverage",
        },
        {
            "code": "LATEST_SNAPSHOT_AGE_MINUTES",
            "status": _level(latest_age, LATEST_AGE_WARN_MINUTES, LATEST_AGE_FAIL_MINUTES),
            "value": latest_age,
            "warn_at": LATEST_AGE_WARN_MINUTES,
            "fail_at": LATEST_AGE_FAIL_MINUTES,
            "policy": "freshness warning; do not use stale data as current status",
        },
    ]

    curated = checks.get("CURATED_GRAIN_UNIQUENESS", {})
    if curated.get("status") == "FAIL":
        metrics.append(
            {
                "code": "CURATED_GRAIN_UNIQUENESS",
                "status": "FAIL",
                "value": curated.get("evidence"),
                "policy": "block DA② handoff until deterministic dedupe succeeds",
            }
        )

    statuses = [item["status"] for item in metrics]
    overall = "FAIL" if "FAIL" in statuses else "WARN" if "WARN" in statuses else "PASS"
    return {
        "checked_at_kst": datetime.now(KST).isoformat(timespec="seconds"),
        "monitor_status": overall,
        "recommendation_ready": overall != "FAIL" and report.get("recommendation_ready", False),
        "source_report": report.get("source_root"),
        "profile": profile,
        "metrics": metrics,
        "validator_summary": report.get("summary"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--history", type=Path, help="optional JSONL history file")
    args = parser.parse_args()

    from validate_recommendation_inputs import build_report
    from loop_paths import LOOP1_SNAPSHOTS, iter_status_csvs

    report = classify_report(build_report(list(iter_status_csvs(LOOP1_SNAPSHOTS))))
    output = args.output if args.output.is_absolute() else REPO / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.history:
        history = args.history if args.history.is_absolute() else REPO / args.history
        history.parent.mkdir(parents=True, exist_ok=True)
        with history.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(report, ensure_ascii=False) + "\n")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"OUT {output.relative_to(REPO)}")
    return 1 if report["monitor_status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
