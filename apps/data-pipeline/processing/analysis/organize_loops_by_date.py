"""Move flat loop1/loop3 CSVs into YYYYMMDD folders.

Usage (repo root):
  python apps/data-pipeline/processing/analysis/organize_loops_by_date.py
  python apps/data-pipeline/processing/analysis/organize_loops_by_date.py --dry-run
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))
from _bootstrap import ensure_paths

REPO = ensure_paths()
from loop_paths import (  # noqa: E402
    LOOP1_SNAPSHOTS,
    LOOP3_DIR,
    ymd_from_filename,
)


def _move(src: Path, dst: Path, *, dry: bool) -> bool:
    if dst.exists():
        if src.resolve() == dst.resolve():
            return False
        # identical name already in day folder — drop flat duplicate
        src.unlink(missing_ok=True)
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dry:
        print(f"DRY {src.relative_to(REPO)} -> {dst.relative_to(REPO)}")
        return True
    shutil.move(str(src), str(dst))
    return True


def organize_loop1(*, dry: bool) -> int:
    n = 0
    if not LOOP1_SNAPSHOTS.is_dir():
        return 0
    for fp in sorted(LOOP1_SNAPSHOTS.glob("daegu_charger_status_*.csv")):
        ymd = ymd_from_filename(fp.name)
        if not ymd:
            print(f"SKIP no-date {fp.name}")
            continue
        dst = LOOP1_SNAPSHOTS / ymd / fp.name
        if _move(fp, dst, dry=dry):
            n += 1
    return n


def organize_loop3(*, dry: bool) -> int:
    n = 0
    if not LOOP3_DIR.is_dir():
        return 0
    for fp in sorted(LOOP3_DIR.glob("daegu_traffic_*.csv")):
        if "latest" in fp.name:
            continue
        ymd = ymd_from_filename(fp.name)
        if not ymd:
            print(f"SKIP no-date {fp.name}")
            continue
        dst = LOOP3_DIR / ymd / fp.name
        if _move(fp, dst, dry=dry):
            n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    n1 = organize_loop1(dry=args.dry_run)
    n3 = organize_loop3(dry=args.dry_run)
    print(f"moved loop1={n1} loop3={n3} dry={args.dry_run}")
    # show sample layout
    days1 = sorted(p.name for p in LOOP1_SNAPSHOTS.glob("20*") if p.is_dir())[-5:]
    days3 = sorted(p.name for p in LOOP3_DIR.glob("20*") if p.is_dir())[-5:]
    print(f"loop1 day folders (tail): {days1}")
    print(f"loop3 day folders (tail): {days3}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
