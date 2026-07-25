"""Read-time loader for collected status snapshots (loop1).

Raw snapshot CSVs under docs/data/loops/loop1/snapshots/ are immutable source data.
Any downstream use (Phase B timeseries, coverage stats, feature building)
should load through here so it always gets a deduplicated view without
mutating the raw files.

Dedup rule: within a single snapshot, keep the first (statId, chgerId).
A charger can appear twice at a page boundary when records shift between
page requests; the duplicate rows are identical, so keeping the first is
lossless.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

_SRC = Path(__file__).resolve().parent
_REPO = Path(__file__).resolve().parents[7]
_DATA_PIPELINE = _REPO / "apps" / "data-pipeline"
if str(_DATA_PIPELINE) not in sys.path:
    sys.path.insert(0, str(_DATA_PIPELINE))

from loop_paths import iter_status_csvs, status_snapshots_dir, status_snapshots_dirs

SNAP_DIR = status_snapshots_dir()


def load_snapshot(path: str | Path) -> pd.DataFrame:
    """Load one snapshot CSV, deduped on (statId, chgerId)."""
    df = pd.read_csv(path, dtype={"statId": str, "chgerId": str})
    return df.drop_duplicates(subset=["statId", "chgerId"], keep="first").reset_index(drop=True)


def load_all_snapshots(snap_dir: str | Path | None = None) -> pd.DataFrame:
    """Load every snapshot, deduped per snapshot, concatenated in time order.

    Dedup is per (snapshotId, statId, chgerId) so the same charger observed in
    different snapshots (different times) is kept — that is the timeseries.
    """
    if snap_dir is not None:
        dirs = [Path(snap_dir)]
    else:
        dirs = status_snapshots_dirs()
    files: list[Path] = []
    seen_names: set[str] = set()
    for directory in dirs:
        for fp in iter_status_csvs(directory):
            if fp.name in seen_names:
                continue
            seen_names.add(fp.name)
            files.append(fp)
    frames = [pd.read_csv(fp, dtype={"statId": str, "chgerId": str}) for fp in files]
    if not frames:
        return pd.DataFrame()
    alldf = pd.concat(frames, ignore_index=True)
    return alldf.drop_duplicates(
        subset=["snapshotId", "statId", "chgerId"], keep="first"
    ).reset_index(drop=True)


if __name__ == "__main__":
    df = load_all_snapshots()
    print(f"loaded rows (deduped): {len(df)}")
    if not df.empty:
        print(f"snapshots: {df['snapshotId'].nunique()}")
        print(f"unique chargers: {df.groupby(['statId', 'chgerId']).ngroups}")
