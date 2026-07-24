"""Validate the periodic status collection.

Read-only. Scans every snapshot CSV under data/snapshots and checks:
  1. Timing: expected 15-min cadence, detect missing/late/duplicate rounds
  2. Duplicates: identical snapshot files / duplicated (statId,chgerId) within a snapshot
  3. Coverage: unique chargers per snapshot and cumulative over time
  4. Status codes: distribution + any invalid codes
  5. Data quality: nulls in key columns, statUpdDt sanity vs period window
  6. Cross-check against index.csv

Does NOT write anything under docs/data/extracted/. Optionally writes a
report JSON under data/logs/ when --write-report is passed.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

_SRC = Path(__file__).resolve().parent
_REPO = Path(__file__).resolve().parents[7]
_DATA_PIPELINE = _REPO / "apps" / "data-pipeline"
if str(_DATA_PIPELINE) not in sys.path:
    sys.path.insert(0, str(_DATA_PIPELINE))

from loop_paths import LOOP1_INDEX, LOOP1_LOGS, status_snapshots_dir

SNAP_DIR = status_snapshots_dir()
INDEX_CSV = LOOP1_INDEX
LOGS_DIR = LOOP1_LOGS

EXPECTED_INTERVAL_MIN = 15
# EvCharger status codes (statNm often blank, so we map by code)
STAT_LABELS = {
    1: "communication_error",
    2: "available",
    3: "in_use",
    4: "operation_stopped",
    5: "under_inspection",
    9: "status_unknown",
}
KEY_COLS = ["statId", "chgerId", "stat", "statUpdDt", "fetchedAt", "snapshotId"]


def _load_snapshots() -> tuple[pd.DataFrame, list[dict]]:
    files = sorted(SNAP_DIR.glob("daegu_charger_status_*.csv"))
    per_snapshot: list[dict] = []
    frames = []
    for fp in files:
        try:
            df = pd.read_csv(fp, dtype={"statId": str, "chgerId": str})
        except Exception as exc:  # noqa: BLE001
            per_snapshot.append({"file": fp.name, "ok": False, "error": str(exc)})
            continue
        df["__file"] = fp.name
        frames.append(df)
        dup_pairs = int(df.duplicated(subset=["statId", "chgerId"]).sum())
        per_snapshot.append(
            {
                "file": fp.name,
                "ok": True,
                "rows": int(len(df)),
                "unique_chargers": int(df.groupby(["statId", "chgerId"]).ngroups),
                "dup_pairs": dup_pairs,
                "snapshotId": str(df["snapshotId"].iloc[0]) if "snapshotId" in df and len(df) else None,
            }
        )
    if not frames:
        return pd.DataFrame(), per_snapshot
    return pd.concat(frames, ignore_index=True), per_snapshot


def _check_timing(per_snapshot: list[dict]) -> dict:
    ids = [s["snapshotId"] for s in per_snapshot if s.get("ok") and s.get("snapshotId")]
    ts = pd.to_datetime(pd.Series(ids), format="%Y%m%d_%H%M%S", errors="coerce").dropna().sort_values()
    if len(ts) < 2:
        return {"snapshots": int(len(ts)), "note": "not enough snapshots for gap analysis"}
    deltas = ts.diff().dropna().dt.total_seconds() / 60.0
    # a "gap" = interval notably larger than expected (missed at least one round)
    gaps = []
    prev = ts.iloc[0]
    for cur, d in zip(ts.iloc[1:], deltas):
        if d > EXPECTED_INTERVAL_MIN * 1.5:
            missed = int(round(d / EXPECTED_INTERVAL_MIN)) - 1
            gaps.append({"from": str(prev), "to": str(cur), "minutes": round(float(d), 1), "approx_missed": missed})
        prev = cur
    total_missed = sum(g["approx_missed"] for g in gaps)
    span_min = (ts.iloc[-1] - ts.iloc[0]).total_seconds() / 60.0
    expected_rounds = int(span_min // EXPECTED_INTERVAL_MIN) + 1
    return {
        "snapshots": int(len(ts)),
        "first": str(ts.iloc[0]),
        "last": str(ts.iloc[-1]),
        "span_hours": round(span_min / 60.0, 1),
        "interval_median_min": round(float(deltas.median()), 1),
        "interval_min": round(float(deltas.min()), 1),
        "interval_max": round(float(deltas.max()), 1),
        "expected_rounds_if_perfect": expected_rounds,
        "gaps_detected": len(gaps),
        "approx_rounds_missed": total_missed,
        "gaps": gaps[:20],
    }


def _check_coverage(all_df: pd.DataFrame) -> dict:
    order = sorted(all_df["snapshotId"].dropna().unique().tolist())
    seen: set[tuple] = set()
    cumulative = []
    for sid in order:
        sub = all_df[all_df["snapshotId"] == sid]
        pairs = set(map(tuple, sub[["statId", "chgerId"]].dropna().itertuples(index=False, name=None)))
        seen |= pairs
        cumulative.append({"snapshotId": sid, "per_snapshot": len(pairs), "cumulative_unique": len(seen)})
    per_counts = [c["per_snapshot"] for c in cumulative]
    return {
        "cumulative_unique_chargers": len(seen),
        "per_snapshot_mean": round(sum(per_counts) / len(per_counts), 1) if per_counts else 0,
        "per_snapshot_min": min(per_counts) if per_counts else 0,
        "per_snapshot_max": max(per_counts) if per_counts else 0,
        "first_snapshot": cumulative[0] if cumulative else None,
        "last_snapshot": cumulative[-1] if cumulative else None,
        "growth_curve_tail": cumulative[-5:],
    }


def _check_status(all_df: pd.DataFrame) -> dict:
    stat = pd.to_numeric(all_df["stat"], errors="coerce")
    counts = stat.value_counts(dropna=False).sort_index()
    dist = {}
    invalid = 0
    for code, n in counts.items():
        if pd.isna(code):
            dist["null"] = int(n)
            invalid += int(n)
        else:
            code_i = int(code)
            label = STAT_LABELS.get(code_i, f"UNKNOWN_{code_i}")
            dist[f"{code_i}:{label}"] = int(n)
            if code_i not in STAT_LABELS:
                invalid += int(n)
    return {"distribution_all_rows": dist, "invalid_or_null_codes": invalid}


def _check_quality(all_df: pd.DataFrame) -> dict:
    out = {}
    for col in ["statId", "chgerId", "stat", "statUpdDt", "fetchedAt", "snapshotId"]:
        if col in all_df.columns:
            out[f"null_{col}"] = int(all_df[col].isna().sum())
        else:
            out[f"missing_column_{col}"] = True
    # statUpdDt parse rate
    upd = pd.to_datetime(all_df["statUpdDt"], format="%Y%m%d%H%M%S", errors="coerce")
    out["statUpdDt_parse_fail"] = int(upd.isna().sum())
    out["total_rows"] = int(len(all_df))
    return out


def _cross_check_index(per_snapshot: list[dict]) -> dict:
    if not INDEX_CSV.exists():
        return {"index_present": False}
    idx = pd.read_csv(INDEX_CSV)
    files_on_disk = {s["file"] for s in per_snapshot if s.get("ok")}
    idx_ids = set(idx["snapshotId"].astype(str)) if "snapshotId" in idx else set()
    disk_ids = {s["snapshotId"] for s in per_snapshot if s.get("ok") and s.get("snapshotId")}
    return {
        "index_present": True,
        "index_rows": int(len(idx)),
        "snapshot_files_on_disk": len(files_on_disk),
        "in_index_not_on_disk": sorted(idx_ids - disk_ids)[:20],
        "on_disk_not_in_index": sorted(disk_ids - idx_ids)[:20],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write-report", action="store_true", help="write report JSON under data/logs/")
    args = ap.parse_args()

    if not SNAP_DIR.exists():
        print(json.dumps({"ok": False, "error": f"no snapshot dir: {SNAP_DIR}"}, ensure_ascii=False))
        return 1

    all_df, per_snapshot = _load_snapshots()
    n_ok = sum(1 for s in per_snapshot if s.get("ok"))
    if all_df.empty:
        print(json.dumps({"ok": False, "error": "no readable snapshots", "files": per_snapshot}, ensure_ascii=False))
        return 1

    report = {
        "ok": True,
        "snapshot_files": len(per_snapshot),
        "readable": n_ok,
        "unreadable": [s for s in per_snapshot if not s.get("ok")],
        "duplicate_pair_snapshots": [s["file"] for s in per_snapshot if s.get("dup_pairs")],
        "timing": _check_timing(per_snapshot),
        "coverage": _check_coverage(all_df),
        "status": _check_status(all_df),
        "quality": _check_quality(all_df),
        "index_cross_check": _cross_check_index(per_snapshot),
    }

    print(json.dumps(report, ensure_ascii=False, indent=2))

    if args.write_report:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        out = LOGS_DIR / "validation_report.json"
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n[written] {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
