"""5-minute / tick status collection quality metrics (loop1)."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .paths import CALL_LOG, LOOP1_INDEX, OUT_FIGURES, OUT_JSON, OUT_TABLES, ensure_out

_SANDBOX_SRC = (
    Path(__file__).resolve().parents[1]
    / "personal/experiments/SANDBOX_20260717_status_periodic_collection/src"
)
if str(_SANDBOX_SRC) not in sys.path:
    sys.path.insert(0, str(_SANDBOX_SRC))

from load_snapshots import load_all_snapshots  # noqa: E402


def _parse_ts(snapshot_id: str) -> pd.Timestamp:
    return pd.to_datetime(snapshot_id, format="%Y%m%d_%H%M%S")


def run_status_quality() -> dict[str, Any]:
    ensure_out()
    idx = pd.read_csv(LOOP1_INDEX, dtype=str) if LOOP1_INDEX.exists() else pd.DataFrame()
    if idx.empty:
        return {"ok": False, "error": "loop1 index missing"}

    idx["ts"] = idx["snapshotId"].map(_parse_ts)
    idx = idx.sort_values("ts").reset_index(drop=True)
    idx["ok_bool"] = idx["ok"].astype(str).str.lower().isin({"true", "1", "yes"})
    idx["gap_min"] = idx["ts"].diff().dt.total_seconds() / 60.0
    gaps = idx["gap_min"].dropna()

    # design target 5 min; observed ops ~10
    within_5 = float((gaps <= 5.5).mean()) if len(gaps) else 0.0
    within_10 = float((gaps <= 10.5).mean()) if len(gaps) else 0.0
    within_15 = float((gaps <= 15.5).mean()) if len(gaps) else 0.0
    gap_ge_10 = float((gaps >= 10).mean()) if len(gaps) else 0.0
    gap_ge_15 = float((gaps >= 15).mean()) if len(gaps) else 0.0
    gap_ge_30 = float((gaps >= 30).mean()) if len(gaps) else 0.0

    # call log
    call_rows = []
    if CALL_LOG.exists():
        for line in CALL_LOG.read_text(encoding="utf-8").splitlines():
            if line.strip():
                call_rows.append(json.loads(line))
    call_df = pd.DataFrame(call_rows)
    success_rate = float(call_df["ok"].mean()) if not call_df.empty and "ok" in call_df else float(idx["ok_bool"].mean())

    # consecutive failures
    fails = (~idx["ok_bool"]).astype(int)
    max_fail_streak = 0
    streak = 0
    for v in fails:
        streak = streak + 1 if v else 0
        max_fail_streak = max(max_fail_streak, streak)

    events = load_all_snapshots()
    events["stat"] = pd.to_numeric(events["stat"], errors="coerce")
    events["ts"] = events["snapshotId"].map(_parse_ts)
    events["statUpdDt_dt"] = pd.to_datetime(events["statUpdDt"], format="%Y%m%d%H%M%S", errors="coerce")
    events["fetchedAt_dt"] = pd.to_datetime(events["fetchedAt"], errors="coerce")
    events["charger_key"] = events["statId"].astype(str) + "|" + events["chgerId"].astype(str)

    # duplicate within snapshot
    dup_rate = float(
        events.duplicated(subset=["snapshotId", "statId", "chgerId"]).mean()
    ) if not events.empty else 0.0

    # time reversal: fetchedAt < previous for same charger
    ev = events.sort_values(["charger_key", "ts"])
    lag_ts = ev.groupby("charger_key")["ts"].shift(1)
    time_reversal = int((ev["ts"] < lag_ts).sum())

    lag_stat = abs((ev["fetchedAt_dt"] - ev["statUpdDt_dt"]).dt.total_seconds() / 60.0)
    age_stats = {
        "fetch_minus_statUpd_min_median": float(lag_stat.median()) if lag_stat.notna().any() else None,
        "fetch_minus_statUpd_min_p95": float(lag_stat.quantile(0.95)) if lag_stat.notna().any() else None,
        "negative_age_count": int((lag_stat < 0).sum()),
    }

    # hourly coverage: unique chargers observed per hour
    ev["hour"] = ev["ts"].dt.hour
    hourly = ev.groupby("hour")["charger_key"].nunique().rename("unique_chargers").reset_index()
    hourly.to_csv(OUT_TABLES / "status_hourly_coverage.csv", index=False, encoding="utf-8-sig")

    # state transitions per charger
    def n_transitions(s: pd.Series) -> int:
        s = s.dropna()
        if len(s) < 2:
            return 0
        return int((s.values[1:] != s.values[:-1]).sum())

    transitions = ev.groupby("charger_key")["stat"].apply(n_transitions)
    # dwell: consecutive same-stat duration using snapshot gaps
    dwell_minutes: list[float] = []
    for _, g in ev.groupby("charger_key"):
        g = g.sort_values("ts")
        if len(g) < 2:
            continue
        prev_stat = g["stat"].iloc[0]
        start = g["ts"].iloc[0]
        for i in range(1, len(g)):
            cur = g["stat"].iloc[i]
            t = g["ts"].iloc[i]
            if cur != prev_stat:
                dwell_minutes.append((t - start).total_seconds() / 60.0)
                start = t
                prev_stat = cur

    dwell = pd.Series(dwell_minutes, dtype=float)
    status_share = ev["stat"].value_counts(normalize=True).sort_index()

    # master match: chargers seen vs info
    info_path = None
    from .paths import charger_info_csvs

    cands = [p for p in charger_info_csvs() if "latest" in p.name] or charger_info_csvs()
    if cands:
        info_path = cands[-1]
        info = pd.read_csv(info_path, dtype={"statId": str, "chgerId": str}, usecols=lambda c: c in {"statId", "chgerId"})
        info["charger_key"] = info["statId"] + "|" + info["chgerId"]
        master_n = info["charger_key"].nunique()
        seen_n = ev["charger_key"].nunique()
        match_rate = float(ev["charger_key"].isin(set(info["charger_key"])).mean())
    else:
        master_n = seen_n = match_rate = None

    # Can we separate unchanged vs collection failure?
    # YES at tick level via index/call_log ok flag.
    # NO at charger level inside a failed tick (no rows).
    # Inside successful tick, absence = change-feed semantics (unchanged OR never seen).
    design = {
        "collection_success_distinguishable": True,
        "how": "loop1/index.csv ok + logs/call_log.jsonl per snapshotId",
        "unchanged_vs_unobserved_at_charger": (
            "Partial: on successful ticks, API period-change feed means non-returned "
            "chargers are 'no change in period' not proven current state; "
            "chargers never seen in series remain unknown."
        ),
        "lastSeenAt_only_would_lose_history": (
            "Yes if only serving table kept — current design stores per-tick change "
            "CSVs so change history is preserved; unbroken same-state confirmations "
            "are NOT stored as rows (must reconstruct with collection_success)."
        ),
        "proposed_tables": [
            "collector_run / collection_log (exists: call_log.jsonl + index.csv)",
            "raw status snapshot (exists: loop1/snapshots/*.csv — change feed)",
            "status change event (derivable from consecutive observations)",
            "latest serving table (D1 / charger_current_view — does not replace history)",
        ],
        "critical_design_gap": (
            "No explicit row for 'polled OK, state unchanged'. Reconstruction must "
            "combine collection_success(tick) + last observed event + max_hold."
        ),
    }

    gap_dist = {
        "n_gaps": int(len(gaps)),
        "median_min": float(gaps.median()) if len(gaps) else None,
        "mean_min": float(gaps.mean()) if len(gaps) else None,
        "p90_min": float(gaps.quantile(0.9)) if len(gaps) else None,
        "max_min": float(gaps.max()) if len(gaps) else None,
        "pct_le_5_5min": within_5,
        "pct_le_10_5min": within_10,
        "pct_le_15_5min": within_15,
        "pct_ge_10min": gap_ge_10,
        "pct_ge_15min": gap_ge_15,
        "pct_ge_30min": gap_ge_30,
        "design_interval_minutes": 5,
        "observed_ops_interval_minutes": 10,
        "five_min_compliance": within_5,
        "ten_min_compliance": within_10,
    }

    result = {
        "ok": True,
        "n_snapshots": int(len(idx)),
        "first_ts": str(idx["ts"].iloc[0]),
        "last_ts": str(idx["ts"].iloc[-1]),
        "n_calendar_days": int(idx["ts"].dt.date.nunique()),
        "api_success_rate": success_rate,
        "max_consecutive_failures": max_fail_streak,
        "gap_distribution": gap_dist,
        "within_snapshot_dup_rate": dup_rate,
        "time_reversal_count": time_reversal,
        "age_stats": age_stats,
        "unique_chargers_observed": int(ev["charger_key"].nunique()),
        "unique_stations_observed": int(ev["statId"].nunique()),
        "event_rows": int(len(ev)),
        "status_share": {str(int(k) if pd.notna(k) else k): float(v) for k, v in status_share.items()},
        "transitions": {
            "median": float(transitions.median()) if len(transitions) else None,
            "mean": float(transitions.mean()) if len(transitions) else None,
            "p95": float(transitions.quantile(0.95)) if len(transitions) else None,
        },
        "dwell_minutes": {
            "n": int(len(dwell)),
            "median": float(dwell.median()) if len(dwell) else None,
            "p05": float(dwell.quantile(0.05)) if len(dwell) else None,
            "p95": float(dwell.quantile(0.95)) if len(dwell) else None,
            "lt_5min_share": float((dwell < 5).mean()) if len(dwell) else None,
            "gt_24h_share": float((dwell > 24 * 60).mean()) if len(dwell) else None,
        },
        "master_match": {
            "info_path": str(info_path).replace("\\", "/") if info_path else None,
            "master_chargers": master_n,
            "seen_chargers": seen_n,
            "event_rows_in_master_rate": match_rate,
        },
        "design": design,
    }

    # tables
    idx[["snapshotId", "rows", "api_calls", "period_minutes", "fetchedAt", "ok"]].assign(
        gap_min=idx["gap_min"]
    ).to_csv(OUT_TABLES / "status_tick_gaps.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(
        [{"stat": k, "share": v} for k, v in result["status_share"].items()]
    ).to_csv(OUT_TABLES / "status_code_share.csv", index=False, encoding="utf-8-sig")

    # figures
    try:
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(8, 4))
        ax.hist(gaps.dropna(), bins=40, color="#2c5f6e")
        ax.axvline(5, color="red", ls="--", label="5 min design")
        ax.axvline(10, color="orange", ls="--", label="10 min ops")
        ax.set_xlabel("Gap between ticks (minutes)")
        ax.set_ylabel("Count")
        ax.set_title("Status collection interval distribution")
        ax.legend()
        fig.tight_layout()
        fig.savefig(OUT_FIGURES / "status_gap_hist.png", dpi=120)
        plt.close(fig)

        fig, ax = plt.subplots(figsize=(8, 4))
        ax.bar(hourly["hour"], hourly["unique_chargers"], color="#2c5f6e")
        ax.set_xlabel("Hour (KST)")
        ax.set_ylabel("Unique chargers observed")
        ax.set_title("Hourly observation coverage (change-feed rows)")
        fig.tight_layout()
        fig.savefig(OUT_FIGURES / "status_hourly_coverage.png", dpi=120)
        plt.close(fig)
    except Exception as exc:  # noqa: BLE001
        result["figure_error"] = str(exc)

    (OUT_JSON / "status_quality.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    return result
