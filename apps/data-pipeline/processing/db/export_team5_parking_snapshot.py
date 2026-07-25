"""Read-only full snapshot of Team5 parking tables.

Exports every currently available parking row, including raw API payloads,
into a timestamped local directory. It never writes to Team5 MySQL.

Usage (repo root):
  python apps/data-pipeline/processing/db/export_team5_parking_snapshot.py
"""
from __future__ import annotations

import json
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
TABLES = ("parking_api_raw", "parking_lot_info", "parking_realtime_status")


def main() -> int:
    now = datetime.now(KST)
    stamp = now.strftime("%Y%m%d_%H%M%S")
    out = EXTRACTED_PARKING / f"team5_full_snapshot_{stamp}"
    out.mkdir(parents=True, exist_ok=True)

    files: dict[str, dict[str, object]] = {}
    with connect() as conn:
        for table in TABLES:
            # Table names are a fixed allow-list, never user input.
            df = pd.read_sql(f"SELECT * FROM `{table}`", conn)
            path = out / f"{table}.csv"
            df.to_csv(path, index=False, encoding="utf-8-sig")
            files[table] = {
                "rows": int(len(df)),
                "columns": list(df.columns),
                "path": str(path.relative_to(REPO)).replace("\\", "/"),
            }

        batches = pd.read_sql(
            """
            SELECT collected_at, COUNT(*) AS rows_n, COUNT(DISTINCT pklt_id) AS lots
            FROM parking_realtime_status
            GROUP BY collected_at
            ORDER BY collected_at
            """,
            conn,
        )
    batches_path = out / "parking_realtime_batches.csv"
    batches.to_csv(batches_path, index=False, encoding="utf-8-sig")
    files["parking_realtime_batches"] = {
        "rows": int(len(batches)),
        "path": str(batches_path.relative_to(REPO)).replace("\\", "/"),
    }

    meta = {
        "as_of_kst": now.isoformat(timespec="seconds"),
        "source": "Team5 MySQL team_5 (read-only)",
        "tables": files,
        "note": (
            "Full local snapshot for DA① analysis. "
            "Continuous Team5 DB polling requires Team5 owner agreement."
        ),
    }
    (out / "snapshot_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    print(f"OUT {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
