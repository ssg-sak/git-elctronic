"""Read-only incremental export of new Team5 parking rows.

The Team5 DB already stores each 10-minute realtime batch. This script copies
only rows whose source-table IDs are newer than the local cursor; it does not
write to Team5 or register an automatic scheduler.

Usage (repo root):
  python apps/data-pipeline/processing/db/export_team5_parking_incremental.py
"""
from __future__ import annotations

import json
import os
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
from db.export_team5_parking_csv import connect  # noqa: E402
from loop_paths import EXTRACTED_PARKING  # noqa: E402

KST = ZoneInfo("Asia/Seoul")
ROOT = EXTRACTED_PARKING / "incremental"
CURSOR_PATH = ROOT / "team5_parking_cursor.json"
SPECS = {
    "parking_realtime_status": "id",
    "parking_lot_info": "id",
    "parking_api_raw": "id",
}


def _baseline_cursor() -> dict[str, int]:
    """Avoid re-exporting rows already captured in the newest full snapshot."""
    hits = sorted(EXTRACTED_PARKING.glob("team5_full_snapshot_*/"))
    if not hits:
        return {table: 0 for table in SPECS}
    snapshot = hits[-1]
    values: dict[str, int] = {}
    for table, id_col in SPECS.items():
        path = snapshot / f"{table}.csv"
        if not path.is_file():
            values[table] = 0
            continue
        ids = pd.to_numeric(pd.read_csv(path, usecols=[id_col])[id_col], errors="coerce")
        values[table] = int(ids.max()) if ids.notna().any() else 0
    return values


def _load_cursor() -> dict[str, int]:
    if not CURSOR_PATH.is_file():
        return _baseline_cursor()
    raw = json.loads(CURSOR_PATH.read_text(encoding="utf-8"))
    return {
        table: int(raw.get("last_ids", {}).get(table, 0))
        for table in SPECS
    }


def main() -> int:
    ROOT.mkdir(parents=True, exist_ok=True)
    now = datetime.now(KST)
    stamp = now.strftime("%Y%m%d_%H%M%S")
    cursor_before = _load_cursor()

    frames: dict[str, pd.DataFrame] = {}
    cursor_after = cursor_before.copy()
    with connect() as conn:
        for table, id_col in SPECS.items():
            last_id = cursor_before[table]
            frame = pd.read_sql(
                f"SELECT * FROM `{table}` WHERE `{id_col}` > %s ORDER BY `{id_col}`",
                conn,
                params=[last_id],
            )
            frames[table] = frame
            if not frame.empty:
                cursor_after[table] = int(pd.to_numeric(frame[id_col]).max())

    out = ROOT / now.strftime("%Y%m%d") / f"team5_parking_incremental_{stamp}"
    out.mkdir(parents=True, exist_ok=True)
    exported: dict[str, dict[str, object]] = {}
    for table, frame in frames.items():
        path = out / f"{table}_new.csv"
        frame.to_csv(path, index=False, encoding="utf-8-sig")
        exported[table] = {
            "rows": int(len(frame)),
            "path": str(path.relative_to(REPO)).replace("\\", "/"),
        }

    meta = {
        "exported_at_kst": now.isoformat(timespec="seconds"),
        "source": "Team5 MySQL team_5 (read-only)",
        "cursor_before": cursor_before,
        "cursor_after": cursor_after,
        "exports": exported,
        "schedule": os.environ.get("TEAM5_EXPORT_SCHEDULE", "manual only"),
    }
    (out / "manifest.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    CURSOR_PATH.write_text(
        json.dumps(
            {
                "updated_at_kst": now.isoformat(timespec="seconds"),
                "last_ids": cursor_after,
                "last_export": str(out.relative_to(REPO)).replace("\\", "/"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    print(f"OUT {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
