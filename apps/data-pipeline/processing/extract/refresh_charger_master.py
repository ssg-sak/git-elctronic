"""On-demand charger_master refresh from latest charger info extract.

Not a daily loop. Run when info extract is newer than master, or after
coord quarantine / service CSV changes.

Usage (repo root):
  python apps/data-pipeline/processing/extract/refresh_charger_master.py
  python apps/data-pipeline/processing/extract/refresh_charger_master.py --force
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

REPO = Path(__file__).resolve().parents[4]
SANDBOX = (
    REPO
    / "apps/data-pipeline/evaluation/personal/experiments"
    / "SANDBOX_20260716_preprocess_pipeline"
)
SRC = SANDBOX / "src"
sys.path.insert(0, str(SRC))
sys.path.insert(0, str(REPO / "apps/data-pipeline/processing"))
sys.path.insert(0, str(REPO / "apps/data-pipeline"))

from loop_paths import EXTRACTED_CHARGER_INFO  # noqa: E402
from preprocessing.clean_charger import clean_charger_info, build_charger_tables  # noqa: E402
from preprocessing.utils import save_table  # noqa: E402

KST = ZoneInfo("Asia/Seoul")
PROC = SANDBOX / "data" / "processed"
MASTER = PROC / "charger_master.csv"
META = PROC / "charger_master_refresh_meta.json"


def _latest_info() -> Path | None:
    # Prefer service (coord_ok) then generic latest
    candidates = []
    for pat in (
        "daegu_charger_info_service_latest.csv",
        "daegu_charger_info_*_latest.csv",
        "daegu_charger_info_*.csv",
    ):
        candidates.extend(EXTRACTED_CHARGER_INFO.glob(pat))
    files = [p for p in candidates if p.is_file() and "quarantine" not in p.name.lower()]
    if not files:
        return None
    # Prefer *service_latest*, else newest mtime
    service = [p for p in files if "service_latest" in p.name]
    if service:
        return service[0]
    return max(files, key=lambda p: p.stat().st_mtime)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    info_path = _latest_info()
    if info_path is None:
        print("FAIL: no charger info CSV under extracted/charger/info")
        return 1

    if MASTER.is_file() and not args.force:
        if MASTER.stat().st_mtime >= info_path.stat().st_mtime:
            meta = {
                "action": "skip",
                "reason": "master newer or equal to info extract",
                "master": str(MASTER.relative_to(REPO)).replace("\\", "/"),
                "info": str(info_path.relative_to(REPO)).replace("\\", "/"),
            "policy": "on-demand only - not a daily loop",
            "as_of_kst": datetime.now(KST).isoformat(timespec="seconds"),
            }
            META.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
            try:
                print(json.dumps(meta, ensure_ascii=False, indent=2))
            except UnicodeEncodeError:
                print(json.dumps(meta, ensure_ascii=True, indent=2))
            return 0

    raw = pd.read_csv(info_path, dtype=str, low_memory=False)
    info_c, quarantine, meta_info = clean_charger_info(raw)
    # status not required for master inventory refresh
    empty_status = pd.DataFrame(
        columns=[
            "pk",
            "stat",
            "stat_mapped",
            "statNm",
            "statUpdDt_dt",
            "fetchedAt_dt",
            "status_age_seconds",
            "is_status_stale",
            "statUpdDt_parse_failed",
        ]
    )
    tables = build_charger_tables(info_c, empty_status)
    PROC.mkdir(parents=True, exist_ok=True)
    save_table(tables["charger_master"], MASTER)
    qpath = PROC / "charger_info_quarantine.csv"
    if quarantine is not None and len(quarantine):
        save_table(quarantine, qpath)

    meta = {
        "action": "refreshed",
        "info": str(info_path.relative_to(REPO)).replace("\\", "/"),
        "master_rows": int(len(tables["charger_master"])),
        "quarantine_rows": int(len(quarantine)) if quarantine is not None else 0,
        "clean_meta": meta_info,
        "policy": "on-demand only - not a daily loop",
        "as_of_kst": datetime.now(KST).isoformat(timespec="seconds"),
    }
    META.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        print(json.dumps(meta, ensure_ascii=False, indent=2, default=str))
    except UnicodeEncodeError:
        print(json.dumps(meta, ensure_ascii=True, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
