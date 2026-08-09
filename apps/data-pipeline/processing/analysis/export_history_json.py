"""Export status snapshots to docs/data/exports/charger-status-history.json (real track)."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

import sys
from pathlib import Path
_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))
from _bootstrap import ensure_paths

REPO = ensure_paths()

from features.status_standard import to_official_status
from loop_paths import status_snapshots_dir

SNAP_DIR = status_snapshots_dir()
OUT = REPO / "docs" / "data" / "exports" / "charger-status-history.json"


def export_snapshots(
    snap_dir: Path | None = None,
    out_path: Path | None = None,
    *,
    limit_files: int | None = None,
) -> dict:
    snap_dir = snap_dir or SNAP_DIR
    out_path = out_path or OUT
    files = sorted(snap_dir.glob("daegu_charger_status_*.csv"))
    if limit_files:
        files = files[-limit_files:]

    frames = []
    for fp in files:
        df = pd.read_csv(fp, dtype={"statId": str, "chgerId": str})
        frames.append(df)
    if not frames:
        raise FileNotFoundError(f"No snapshots under {snap_dir}")

    raw = pd.concat(frames, ignore_index=True)
    raw = raw.drop_duplicates(
        subset=["snapshotId", "statId", "chgerId"], keep="first"
    )

    records = []
    for row in raw.itertuples(index=False):
        stat_raw = getattr(row, "stat", None)
        stat_upd = getattr(row, "statUpdDt", None)
        fetched = getattr(row, "fetchedAt", None)
        snap = getattr(row, "snapshotId", None)
        if fetched and str(fetched) != "nan":
            observed = pd.Timestamp(fetched)
            if observed.tzinfo is None:
                observed = observed.tz_localize("Asia/Seoul")
        elif snap:
            observed = pd.Timestamp(str(snap), format="%Y%m%d_%H%M%S").tz_localize(
                "Asia/Seoul"
            )
        else:
            continue

        if stat_upd and str(stat_upd) != "nan":
            status_upd = pd.Timestamp(str(stat_upd), format="%Y%m%d%H%M%S").tz_localize(
                "Asia/Seoul"
            )
        else:
            status_upd = observed

        records.append(
            {
                "stationId": str(row.statId),
                "chargerId": str(row.chgerId),
                "status": to_official_status(str(stat_raw)),
                "statusUpdatedAt": status_upd.isoformat(),
                "observedAt": observed.isoformat(),
            }
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {
        "snapshot_files": len(files),
        "records": len(records),
        "output": str(out_path.relative_to(REPO)).replace("\\", "/"),
    }


def main() -> int:
    meta = export_snapshots()
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
