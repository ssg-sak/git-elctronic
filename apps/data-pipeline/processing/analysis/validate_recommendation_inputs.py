"""Validate loop1 status history for recommendation-time use.

This check focuses on the DA① → DA② handoff contract:

* grain: one row per snapshotId × statId × chgerId
* event time: statUpdDt
* observation time: fetchedAt
* recommendation cutoff: snapshotId/as_of

It does not claim that a currently available charger will remain available.
It only verifies that the historical inputs are safe to use for an
arrival-time replay without duplicate grain or time-travel leakage.

Usage from repository root:
  python apps/data-pipeline/processing/analysis/validate_recommendation_inputs.py
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))

from _bootstrap import ensure_paths

REPO = ensure_paths()

from loop_paths import LOOP1_SNAPSHOTS, iter_status_csvs  # noqa: E402

KST = ZoneInfo("Asia/Seoul")
REQUIRED_COLUMNS = {
    "statId",
    "chgerId",
    "stat",
    "statUpdDt",
    "fetchedAt",
    "snapshotId",
}
KEY_COLUMNS = ["snapshotId", "statId", "chgerId"]
VALID_STATUS_CODES = {1, 2, 3, 4, 5, 9}
FILENAME_STAMP = re.compile(r"_(20\d{6}_\d{6})\.csv$")
DEFAULT_OUTPUT = (
    REPO / "docs" / "data" / "quality" / "recommendation_input_quality_latest.json"
)


def _status(ok: bool, *, warning: bool = False) -> str:
    if not ok:
        return "FAIL"
    return "WARN" if warning else "PASS"


def _check(code: str, status: str, evidence: object, why: str) -> dict[str, object]:
    return {
        "code": code,
        "status": status,
        "evidence": evidence,
        "why_it_matters": why,
    }


def _parse_snapshot_id(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, format="%Y%m%d_%H%M%S", errors="coerce")


def _parse_stat_updated(series: pd.Series) -> pd.Series:
    return pd.to_datetime(
        series.astype("string").str.replace(r"\.0$", "", regex=True),
        format="%Y%m%d%H%M%S",
        errors="coerce",
    )


def load_snapshots(files: list[Path]) -> tuple[pd.DataFrame, dict[str, object]]:
    frames: list[pd.DataFrame] = []
    unreadable: list[dict[str, str]] = []
    missing_columns: dict[str, list[str]] = {}
    multiple_snapshot_ids: list[str] = []
    filename_snapshot_mismatches: list[str] = []

    for path in files:
        try:
            frame = pd.read_csv(
                path,
                dtype={
                    "statId": "string",
                    "chgerId": "string",
                    "stat": "string",
                    "statUpdDt": "string",
                    "fetchedAt": "string",
                    "snapshotId": "string",
                },
            )
        except Exception as exc:  # noqa: BLE001
            unreadable.append({"file": path.name, "error": str(exc)})
            continue

        missing = sorted(REQUIRED_COLUMNS - set(frame.columns))
        if missing:
            missing_columns[path.name] = missing
            continue

        snapshot_ids = frame["snapshotId"].dropna().unique().tolist()
        if len(snapshot_ids) != 1:
            multiple_snapshot_ids.append(path.name)

        match = FILENAME_STAMP.search(path.name)
        if match and snapshot_ids and str(snapshot_ids[0]) != match.group(1):
            filename_snapshot_mismatches.append(path.name)

        frame["source_file"] = str(path.relative_to(REPO)).replace("\\", "/")
        frames.append(frame)

    combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    file_meta = {
        "requested_files": len(files),
        "readable_files": len(frames),
        "unreadable_files": unreadable,
        "files_missing_required_columns": missing_columns,
        "files_with_multiple_snapshot_ids": multiple_snapshot_ids,
        "filename_snapshot_mismatches": filename_snapshot_mismatches,
    }
    return combined, file_meta


def build_report(files: list[Path]) -> dict[str, object]:
    data, file_meta = load_snapshots(files)
    checks: list[dict[str, object]] = []

    checks.append(
        _check(
            "READABLE_FILES",
            _status(
                file_meta["readable_files"] == file_meta["requested_files"]
                and not file_meta["files_missing_required_columns"]
            ),
            file_meta,
            "Unreadable files or missing columns break the replay population.",
        )
    )

    if data.empty:
        return {
            "checked_at_kst": datetime.now(KST).isoformat(timespec="seconds"),
            "dataset": "loop1 status snapshots",
            "grain": "snapshotId × statId × chgerId",
            "recommendation_ready": False,
            "checks": checks,
        }

    for column in KEY_COLUMNS:
        data[column] = data[column].astype("string").str.strip()

    stat_numeric = pd.to_numeric(data["stat"], errors="coerce")
    fetched_at = pd.to_datetime(data["fetchedAt"], errors="coerce")
    stat_updated_at = _parse_stat_updated(data["statUpdDt"])
    snapshot_at = _parse_snapshot_id(data["snapshotId"])

    duplicate_mask = data.duplicated(subset=KEY_COLUMNS, keep=False)
    duplicate_grain = int(data.duplicated(subset=KEY_COLUMNS).sum())
    duplicate_groups = int(
        data.loc[duplicate_mask, KEY_COLUMNS].drop_duplicates().shape[0]
    )
    duplicate_affected_snapshots = int(
        data.loc[duplicate_mask, "snapshotId"].nunique()
    )
    duplicate_status_conflicts = int(
        (
            data.loc[duplicate_mask]
            .groupby(KEY_COLUMNS, dropna=False)["stat"]
            .nunique()
            > 1
        ).sum()
    )
    null_key_rows = int(data[KEY_COLUMNS].isna().any(axis=1).sum())
    duplicate_snapshot_ids = int(
        data[["snapshotId", "source_file"]]
        .drop_duplicates()
        .duplicated(subset=["snapshotId"])
        .sum()
    )
    invalid_status_rows = int(
        stat_numeric.isna().sum() + (~stat_numeric.dropna().isin(VALID_STATUS_CODES)).sum()
    )
    fetched_parse_fail = int(fetched_at.isna().sum())
    stat_updated_parse_fail = int(stat_updated_at.isna().sum())
    snapshot_parse_fail = int(snapshot_at.isna().sum())

    # A small clock-skew allowance avoids flagging harmless second-level drift.
    future_event_rows = int(
        (
            stat_updated_at.notna()
            & fetched_at.notna()
            & (stat_updated_at > fetched_at + pd.Timedelta(minutes=5))
        ).sum()
    )
    fetched_before_snapshot_rows = int(
        (
            fetched_at.notna()
            & snapshot_at.notna()
            & (fetched_at + pd.Timedelta(minutes=5) < snapshot_at)
        ).sum()
    )

    curated = data.assign(
        __stat_updated_sort=stat_updated_at,
        __page_sort=pd.to_numeric(data.get("pageNo"), errors="coerce").fillna(-1),
        __row_sort=range(len(data)),
    )
    curated = (
        curated.sort_values(
            KEY_COLUMNS
            + ["__stat_updated_sort", "__page_sort", "__row_sort"],
            na_position="first",
        )
        .drop_duplicates(subset=KEY_COLUMNS, keep="last")
        .drop(columns=["__stat_updated_sort", "__page_sort", "__row_sort"])
    )
    curated_duplicate_rows = int(curated.duplicated(subset=KEY_COLUMNS).sum())

    checks.extend(
        [
            _check(
                "RAW_GRAIN_UNIQUENESS",
                _status(
                    null_key_rows == 0,
                    warning=duplicate_grain > 0,
                ),
                {
                    "duplicate_extra_rows": duplicate_grain,
                    "duplicate_groups": duplicate_groups,
                    "affected_snapshots": duplicate_affected_snapshots,
                    "conflicting_status_groups": duplicate_status_conflicts,
                    "null_key_rows": null_key_rows,
                    "total_rows": int(len(data)),
                    "duplicate_rate": round(duplicate_grain / len(data), 6),
                    "remediation": (
                        "Within each snapshotId × statId × chgerId, keep the row "
                        "with the latest statUpdDt; break ties by pageNo and row order."
                    ),
                },
                "Raw page-boundary duplicates can inflate availability before cleansing.",
            ),
            _check(
                "CURATED_GRAIN_UNIQUENESS",
                _status(curated_duplicate_rows == 0),
                {
                    "raw_rows": int(len(data)),
                    "curated_rows": int(len(curated)),
                    "removed_rows": int(len(data) - len(curated)),
                    "remaining_duplicate_rows": curated_duplicate_rows,
                },
                "The DA① handoff must contain one deterministic row per charger and snapshot.",
            ),
            _check(
                "SNAPSHOT_ID_UNIQUENESS",
                _status(
                    duplicate_snapshot_ids == 0
                    and not file_meta["files_with_multiple_snapshot_ids"]
                    and not file_meta["filename_snapshot_mismatches"]
                ),
                {
                    "snapshot_ids_in_multiple_files": duplicate_snapshot_ids,
                    "files_with_multiple_snapshot_ids": len(
                        file_meta["files_with_multiple_snapshot_ids"]
                    ),
                    "filename_snapshot_mismatches": len(
                        file_meta["filename_snapshot_mismatches"]
                    ),
                },
                "Ambiguous snapshot identity prevents a deterministic as-of cutoff.",
            ),
            _check(
                "STATUS_CODE_VALIDITY",
                _status(invalid_status_rows == 0),
                {
                    "invalid_or_null_rows": invalid_status_rows,
                    "allowed": sorted(VALID_STATUS_CODES),
                },
                "Unknown status codes must not be interpreted as available.",
            ),
            _check(
                "TIMESTAMP_PARSE",
                _status(
                    fetched_parse_fail == 0
                    and stat_updated_parse_fail == 0
                    and snapshot_parse_fail == 0
                ),
                {
                    "fetchedAt_parse_fail": fetched_parse_fail,
                    "statUpdDt_parse_fail": stat_updated_parse_fail,
                    "snapshotId_parse_fail": snapshot_parse_fail,
                },
                "Unparseable timestamps cannot participate in arrival-time replay.",
            ),
            _check(
                "NO_TIME_TRAVEL",
                _status(future_event_rows == 0 and fetched_before_snapshot_rows == 0),
                {
                    "stat_updated_over_5m_after_fetch": future_event_rows,
                    "snapshot_over_5m_after_fetch": fetched_before_snapshot_rows,
                },
                "Future information would leak the outcome into recommendation features.",
            ),
        ]
    )

    snapshot_times = (
        pd.Series(snapshot_at.dropna().unique()).sort_values().reset_index(drop=True)
    )
    intervals = snapshot_times.diff().dropna().dt.total_seconds() / 60
    latest_snapshot = snapshot_times.iloc[-1] if len(snapshot_times) else None
    now_naive_kst = datetime.now(KST).replace(tzinfo=None)
    age_minutes = (
        round((now_naive_kst - latest_snapshot.to_pydatetime()).total_seconds() / 60, 1)
        if latest_snapshot is not None
        else None
    )
    latest_rows = (
        data[data["snapshotId"] == latest_snapshot.strftime("%Y%m%d_%H%M%S")]
        if latest_snapshot is not None
        else data.iloc[0:0]
    )
    latest_status = pd.to_numeric(latest_rows["stat"], errors="coerce")

    warn_or_fail = [item for item in checks if item["status"] != "PASS"]
    failed = [item for item in checks if item["status"] == "FAIL"]

    return {
        "checked_at_kst": datetime.now(KST).isoformat(timespec="seconds"),
        "dataset": "AWS Lightsail loop1 status snapshots merged locally",
        "grain": "snapshotId × statId × chgerId",
        "source_root": str(LOOP1_SNAPSHOTS.relative_to(REPO)).replace("\\", "/"),
        "profile": {
            "files": len(files),
            "raw_rows": int(len(data)),
            "curated_rows": int(len(curated)),
            "snapshot_count": int(data["snapshotId"].nunique()),
            "charger_count": int(data.groupby(["statId", "chgerId"]).ngroups),
            "first_snapshot_kst": (
                snapshot_times.iloc[0].isoformat() if len(snapshot_times) else None
            ),
            "latest_snapshot_kst": (
                latest_snapshot.isoformat() if latest_snapshot is not None else None
            ),
            "latest_local_age_minutes": age_minutes,
            "cadence_median_minutes": (
                round(float(intervals.median()), 2) if len(intervals) else None
            ),
            "cadence_p95_minutes": (
                round(float(intervals.quantile(0.95)), 2) if len(intervals) else None
            ),
            "latest_rows": int(len(latest_rows)),
            "latest_available_rows": int((latest_status == 2).sum()),
        },
        "checks": checks,
        "summary": {
            "PASS": sum(item["status"] == "PASS" for item in checks),
            "WARN": sum(item["status"] == "WARN" for item in checks),
            "FAIL": len(failed),
        },
        "recommendation_ready": not failed,
        "open_issues": [item["code"] for item in warn_or_fail],
        "interpretation": (
            "Input quality only. This does not guarantee that an available charger "
            "remains available until arrival."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="JSON report path",
    )
    parser.add_argument(
        "--fail-on-error",
        action="store_true",
        help="return exit code 1 when a FAIL check exists",
    )
    args = parser.parse_args()

    files = list(iter_status_csvs(LOOP1_SNAPSHOTS))
    report = build_report(files)
    output = args.output if args.output.is_absolute() else REPO / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"OUT {output.relative_to(REPO)}")
    if args.fail_on_error and not report["recommendation_ready"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
