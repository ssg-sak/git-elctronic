"""Daily status CSV rollup from immutable per-tick snapshots."""
from __future__ import annotations

import csv
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from load_snapshots import load_all_snapshots

_SRC = Path(__file__).resolve().parent
_REPO = Path(__file__).resolve().parents[7]
import sys

_DATA_PIPELINE = _REPO / "apps" / "data-pipeline"
if str(_DATA_PIPELINE) not in sys.path:
    sys.path.insert(0, str(_DATA_PIPELINE))

from loop_paths import LOOP1_DAILY

DAILY_ROOT = LOOP1_DAILY
DAILY_INDEX = DAILY_ROOT / "index.csv"
KST = ZoneInfo("Asia/Seoul")

STATUS_FIELDS = [
    "statId",
    "chgerId",
    "stat",
    "statNm",
    "statUpdDt",
    "fetchedAt",
    "snapshotId",
    "pageNo",
]

INDEX_FIELDS = [
    "exportDate",
    "path",
    "snapshots",
    "rawRows",
    "dedupRows",
    "firstSnapshot",
    "lastSnapshot",
]


def _append_index(row: dict[str, str | int]) -> None:
    DAILY_ROOT.mkdir(parents=True, exist_ok=True)
    exists = DAILY_INDEX.exists()
    with DAILY_INDEX.open("a", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=INDEX_FIELDS)
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def export_daily_status_csv(report_date: date, *, force: bool = False) -> dict[str, object]:
    """Merge one day's snapshots into a single long CSV under data/daily/."""
    export_date = report_date.isoformat()
    day_dir = DAILY_ROOT / export_date
    stamp = export_date.replace("-", "")
    out_path = day_dir / f"daegu_charger_status_{stamp}_daily.csv"
    latest_path = day_dir / f"daegu_charger_status_{stamp}_latest.csv"

    if out_path.exists() and not force:
        return {
            "generated": False,
            "reason": "already_exists",
            "path": str(out_path),
            "export_date": export_date,
        }

    all_df = load_all_snapshots()
    if all_df.empty:
        return {
            "generated": False,
            "reason": "no_snapshots",
            "export_date": export_date,
        }

    all_df["snapshot_ts"] = pd.to_datetime(
        all_df["snapshotId"], format="%Y%m%d_%H%M%S", errors="coerce"
    )
    daily_df = all_df[all_df["snapshot_ts"].dt.date == report_date].copy()
    if daily_df.empty:
        return {
            "generated": False,
            "reason": "no_snapshots_for_date",
            "export_date": export_date,
        }

    raw_rows = int(len(daily_df))
    daily_df = daily_df.drop_duplicates(
        subset=["snapshotId", "statId", "chgerId"], keep="first"
    ).sort_values(["snapshot_ts", "statId", "chgerId"])
    dedup_rows = int(len(daily_df))
    snapshot_ids = daily_df["snapshotId"].drop_duplicates().sort_values()

    day_dir.mkdir(parents=True, exist_ok=True)
    daily_df[STATUS_FIELDS].to_csv(out_path, index=False, encoding="utf-8-sig")
    latest_path.write_bytes(out_path.read_bytes())

    first_snapshot = snapshot_ids.iloc[0]
    last_snapshot = snapshot_ids.iloc[-1]
    _append_index(
        {
            "exportDate": export_date,
            "path": str(out_path.relative_to(_REPO)).replace("\\", "/"),
            "snapshots": int(snapshot_ids.nunique()),
            "rawRows": raw_rows,
            "dedupRows": dedup_rows,
            "firstSnapshot": first_snapshot,
            "lastSnapshot": last_snapshot,
        }
    )
    return {
        "generated": True,
        "export_date": export_date,
        "path": str(out_path),
        "snapshots": int(snapshot_ids.nunique()),
        "raw_rows": raw_rows,
        "dedup_rows": dedup_rows,
        "first_snapshot": first_snapshot,
        "last_snapshot": last_snapshot,
    }


def export_yesterday_status_csv(*, force: bool = False) -> dict[str, object]:
    yesterday = datetime.now(tz=KST).date() - timedelta(days=1)
    return export_daily_status_csv(yesterday, force=force)


def main() -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Export one day's status snapshots to daily CSV")
    parser.add_argument("--date", help="YYYY-MM-DD (default: yesterday KST)")
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--backfill-from",
        help="Backfill from this date (YYYY-MM-DD) through yesterday, inclusive",
    )
    args = parser.parse_args()

    if args.backfill_from:
        start = date.fromisoformat(args.backfill_from)
        end = datetime.now(tz=KST).date() - timedelta(days=1)
        results = []
        current = start
        while current <= end:
            results.append(export_daily_status_csv(current, force=args.force))
            current += timedelta(days=1)
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0

    target = (
        date.fromisoformat(args.date)
        if args.date
        else datetime.now(tz=KST).date() - timedelta(days=1)
    )
    result = export_daily_status_csv(target, force=args.force)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("generated") or result.get("reason") == "already_exists" else 1


if __name__ == "__main__":
    raise SystemExit(main())
