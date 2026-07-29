"""Build daily trend tables for DA① loop1 collection quality."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))

from _bootstrap import ensure_paths

REPO = ensure_paths()
KST = ZoneInfo("Asia/Seoul")
DEFAULT_OUT = REPO / "docs" / "data" / "quality"
KEYS = ["snapshotId", "statId", "chgerId"]


def build_daily_table() -> pd.DataFrame:
    from loop_paths import LOOP1_SNAPSHOTS, iter_status_csvs

    rows = []
    for path in iter_status_csvs(LOOP1_SNAPSHOTS):
        frame = pd.read_csv(path, dtype="string")
        snapshot_ids = frame["snapshotId"].dropna().unique().tolist()
        snapshot_id = str(snapshot_ids[0]) if snapshot_ids else path.stem.rsplit("_", 2)[-1]
        snapshot_at = pd.to_datetime(snapshot_id, format="%Y%m%d_%H%M%S", errors="coerce")
        duplicate_extra = int(frame.duplicated(KEYS).sum())
        duplicate_groups = int(frame.loc[frame.duplicated(KEYS, keep=False), KEYS].drop_duplicates().shape[0])
        conflict_groups = int(
            (
                frame.loc[frame.duplicated(KEYS, keep=False)]
                .groupby(KEYS, dropna=False)["stat"]
                .nunique()
                > 1
            ).sum()
        )
        rows.append(
            {
                "date": snapshot_at.strftime("%Y-%m-%d") if pd.notna(snapshot_at) else None,
                "snapshot_id": snapshot_id,
                "snapshot_at_kst": snapshot_at.isoformat() if pd.notna(snapshot_at) else None,
                "raw_rows": int(len(frame)),
                "duplicate_extra_rows": duplicate_extra,
                "duplicate_groups": duplicate_groups,
                "duplicate_rate": round(duplicate_extra / len(frame), 6) if len(frame) else None,
                "conflicting_status_groups": conflict_groups,
            }
        )

    snapshots = pd.DataFrame(rows).dropna(subset=["snapshot_at_kst"])
    snapshots["snapshot_at"] = pd.to_datetime(snapshots["snapshot_at_kst"])
    snapshots["date"] = snapshots["snapshot_at"].dt.strftime("%Y-%m-%d")
    snapshots = snapshots.sort_values("snapshot_at")
    snapshots["interval_minutes"] = snapshots["snapshot_at"].diff().dt.total_seconds() / 60
    grouped = []
    now = pd.Timestamp.now(tz=KST).tz_localize(None)
    for date, group in snapshots.groupby("date", sort=True):
        latest = group.iloc[-1]
        intervals = group["interval_minutes"].dropna()
        grouped.append(
            {
                "date": date,
                "snapshot_count": int(len(group)),
                "raw_rows": int(group["raw_rows"].sum()),
                "duplicate_extra_rows": int(group["duplicate_extra_rows"].sum()),
                "duplicate_rate": round(
                    group["duplicate_extra_rows"].sum() / group["raw_rows"].sum(), 6
                ),
                "conflicting_status_groups": int(group["conflicting_status_groups"].sum()),
                "cadence_median_minutes": round(float(intervals.median()), 2) if len(intervals) else None,
                "cadence_p95_minutes": round(float(intervals.quantile(0.95)), 2) if len(intervals) else None,
                "first_snapshot_kst": group.iloc[0]["snapshot_at_kst"],
                "latest_snapshot_kst": latest["snapshot_at_kst"],
                "latest_snapshot_age_minutes_at_report": round(
                    (now - latest["snapshot_at"]).total_seconds() / 60, 1
                ),
            }
        )
    return pd.DataFrame(grouped)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    table = build_daily_table()
    out = args.output_dir if args.output_dir.is_absolute() else REPO / args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    csv_path = out / "daily_quality_trend_20260729.csv"
    json_path = out / "daily_quality_trend_20260729_summary.json"
    table.to_csv(csv_path, index=False, encoding="utf-8-sig")
    summary = {
        "generated_at_kst": pd.Timestamp.now(tz=KST).isoformat(timespec="seconds"),
        "days": int(len(table)),
        "first_date": table["date"].min() if len(table) else None,
        "last_date": table["date"].max() if len(table) else None,
        "columns": table.columns.tolist(),
        "interpretation": "latest_snapshot_age is measured at report-generation time; historical rows show the latest snapshot timestamp for each day.",
    }
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(table.to_string(index=False))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"OUT {csv_path.relative_to(REPO)}")
    print(f"OUT {json_path.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
