"""Final GO / CONDITIONAL GO / NO-GO verdict for ETA-at-arrival goal."""
from __future__ import annotations

import json
from typing import Any

from .paths import OUT_JSON, ensure_out


def run_verdict(bundle: dict[str, Any]) -> dict[str, Any]:
    ensure_out()
    sq = bundle.get("status_quality") or {}
    panel = bundle.get("panel_restore") or {}
    eta = bundle.get("eta_targets") or {}
    usage = bundle.get("usage_eda") or {}
    bt = bundle.get("backtest") or {}

    eta15 = (eta.get("eta15") or {})
    labeled = int(eta15.get("labeled_rows") or 0)
    coverage = float(eta15.get("coverage") or 0)
    days = int(eta15.get("dates_with_label") or 0)
    gap_med = ((sq.get("gap_distribution") or {}).get("median_min"))
    five_comp = float((sq.get("gap_distribution") or {}).get("pct_le_5_5min") or 0)
    design_gap = (sq.get("design") or {}).get("critical_design_gap")
    usage_ok = bool(usage.get("ok"))
    temporal = bool(eta.get("temporal_split_feasible"))
    panel_ok = bool(panel.get("ok")) and not panel.get("impossible")

    # Decision rules (honest)
    structural_blockers = []
    if not panel_ok:
        structural_blockers.append("panel restore failed")
    if labeled == 0:
        structural_blockers.append("zero ETA-15 observed labels")
    # Change-feed + short history are fixable → not automatic NO-GO

    fixable = []
    if five_comp < 0.5:
        fixable.append(f"5-min compliance {five_comp:.1%} (ops~10m) — retune interval to 5")
    if days < 14:
        fixable.append(f"only {days} labeled calendar days — need ≥14 for ML gate")
    if coverage < 0.2:
        fixable.append(f"ETA15 label coverage {coverage:.1%} — denser status or full snapshot mode")
    if design_gap:
        fixable.append("no explicit unchanged confirmation rows — keep collection_log + event model")

    # Grade
    if labeled == 0 or not panel_ok:
        grade = "C_NO_GO"
    elif (
        labeled >= 5000
        and days >= 14
        and temporal
        and five_comp >= 0.5
        and coverage >= 0.25
        and bt.get("ok")
    ):
        grade = "A_GO"
    else:
        grade = "B_CONDITIONAL_GO"

    # Required collection period estimate
    # Assume ~100 labeled rows/day currently if days>0
    per_day = labeled / max(days, 1)
    need_labels = 5000
    days_needed = int(np_ceil(need_labels / max(per_day, 1))) if labeled else 30

    alt_goal = None
    if grade != "A_GO":
        alt_goal = (
            "도착 시 사용 가능성(ETA)을 확률로 보장하기보다, "
            "실시간 관측 가용·신뢰도·과거 일별 이용량 보조 피처로 "
            "규칙 기반 추천 MVP를 유지하고, status를 5분·연속 수집해 ETA 타깃을 축적한다."
        )

    evidence = [
        f"status ticks={sq.get('n_snapshots')} · gap median={gap_med}min · 5m compliance={five_comp:.1%}",
        f"panel cells observed/imputed/null rates={panel.get('observed_rate')}/{panel.get('impute_rate')}/{panel.get('null_rate')}",
        f"ETA15 labeled={labeled} coverage={coverage:.1%} days={days} pos_rate={eta15.get('positive_rate')}",
        f"usage daily rows={usage.get('rows')} (2025={usage.get('rows_2025')}) — auxiliary only, not ETA target",
        f"backtest skipped={bt.get('skipped')} ok={bt.get('ok')} reason={bt.get('reason')}",
    ]

    verdict = {
        "grade": grade,
        "grade_label": {
            "A_GO": "GO",
            "B_CONDITIONAL_GO": "CONDITIONAL GO",
            "C_NO_GO": "NO-GO",
        }[grade],
        "core_evidence": evidence,
        "critical_issues": structural_blockers
        + (
            [
                "Change-feed status: absence ≠ unavailable; ETA labels require actual observation at horizon",
                "Collector currently ~10 min not 5 min design",
            ]
            if grade != "A_GO"
            else []
        ),
        "fixable_issues": fixable,
        "min_collection_period_days": max(days_needed, 14),
        "solvable_in_project_schedule": grade != "C_NO_GO",
        "core_goal_retainable": grade != "C_NO_GO",
        "goal_rewrite_if_needed": alt_goal,
        "usage_role": usage.get("role_verdict"),
        "recommendation": (
            "Keep project: rule-based MVP + usage auxiliaries; enforce 5-min status loop; "
            "re-run ML gate after ≥14 labeled calendar days (labels already plentiful when coverage exists)."
            if grade == "B_CONDITIONAL_GO"
            else (
                "Proceed to controlled ML with walk-forward; keep rule fallback."
                if grade == "A_GO"
                else "Stop ETA claim until collection/schema fixed."
            )
        ),
    }
    (OUT_JSON / "verdict.json").write_text(
        json.dumps(verdict, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    return verdict


def np_ceil(x: float) -> int:
    import math

    return int(math.ceil(x))
