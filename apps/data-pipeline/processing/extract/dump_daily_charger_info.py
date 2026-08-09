"""Fixed-condition daily EvCharger info dump (coverage-gap step 3).

Contract (do not change casually):
  - API: getChargerInfo
  - zcode=27 (대구)
  - numOfRows=999
  - full item columns + fetchedAt (includes limitYn)

Writes:
  docs/data/extracted/daily/YYYY-MM-DD/daegu_charger_info_{stamp}.csv
  docs/data/extracted/daily/YYYY-MM-DD/daegu_charger_info_{ymd}_latest.csv
  docs/data/extracted/charger/info/daegu_charger_info_{stamp}.csv
  docs/data/extracted/charger/info/daegu_charger_info_latest.csv
  docs/data/extracted/daily/index.csv (append)
  docs/data/extracted/daily/YYYY-MM-DD/info_dump_meta.json  (K12 diff)

Quota: ~totalCount/999 EvCharger calls (~25–30). Skip if today's latest
exists unless --force.

Usage (repo root):
  python apps/data-pipeline/processing/extract/dump_daily_charger_info.py
  python apps/data-pipeline/processing/extract/dump_daily_charger_info.py --force
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))
from _bootstrap import ensure_paths

REPO = ensure_paths()
from loop_paths import EXTRACTED_CHARGER_INFO, EXTRACTED_DAILY, daily_charger_info_latests
from zoneinfo import ZoneInfo

from extract_refresh_charger_weather import _key, extract_charger_info

KST = ZoneInfo("Asia/Seoul")
INDEX_PATH = EXTRACTED_DAILY / "index.csv"
INDEX_FIELDS = ["exportDate", "kind", "path", "rows", "fetchedAt", "source"]
SOURCE = "api_getChargerInfo_z27_n999"


def _append_index(
    *,
    export_date: str,
    path: Path,
    rows: int,
    fetched_at: str,
) -> None:
    EXTRACTED_DAILY.mkdir(parents=True, exist_ok=True)
    exists = INDEX_PATH.exists()
    with INDEX_PATH.open("a", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=INDEX_FIELDS)
        if not exists:
            writer.writeheader()
        writer.writerow(
            {
                "exportDate": export_date,
                "kind": "charger_info",
                "path": str(path.relative_to(REPO)).replace("\\", "/"),
                "rows": rows,
                "fetchedAt": fetched_at,
                "source": SOURCE,
            }
        )


def _stat_ids(path: Path) -> set[str]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or "statId" not in reader.fieldnames:
            return set()
        return {str(r.get("statId", "")).strip() for r in reader if str(r.get("statId", "")).strip()}


def _k12_vs_previous(today_latest: Path) -> dict:
    others = [
        p for p in daily_charger_info_latests() if p.resolve() != today_latest.resolve()
    ]
    if not others:
        return {
            "prev_path": None,
            "n_added": None,
            "n_removed": None,
            "note": "no previous daily latest for K12 diff",
        }
    prev = others[-1]
    cur_ids = _stat_ids(today_latest)
    prev_ids = _stat_ids(prev)
    added = sorted(cur_ids - prev_ids)
    removed = sorted(prev_ids - cur_ids)
    return {
        "prev_path": str(prev.relative_to(REPO)).replace("\\", "/"),
        "prev_statIds": len(prev_ids),
        "cur_statIds": len(cur_ids),
        "n_added": len(added),
        "n_removed": len(removed),
        "added_statIds_sample": added[:30],
        "removed_statIds_sample": removed[:30],
    }


def today_latest_path(export_date: str | None = None) -> Path:
    d = export_date or datetime.now(KST).date().isoformat()
    ymd = d.replace("-", "")
    return EXTRACTED_DAILY / d / f"daegu_charger_info_{ymd}_latest.csv"


def run(*, force: bool = False) -> dict:
    now = datetime.now(KST)
    export_date = now.date().isoformat()
    ymd = export_date.replace("-", "")
    stamp = now.strftime("%Y%m%d_%H%M%S")
    day_dir = EXTRACTED_DAILY / export_date
    day_latest = day_dir / f"daegu_charger_info_{ymd}_latest.csv"

    if day_latest.exists() and not force:
        meta = {
            "ok": True,
            "skipped": True,
            "reason": "today_latest_exists",
            "export_date": export_date,
            "latest": str(day_latest.relative_to(REPO)).replace("\\", "/"),
            "hint": "pass --force to re-fetch (~25-30 EvCharger API calls)",
        }
        print(json.dumps(meta, ensure_ascii=True, indent=2))
        return meta

    key = _key()
    EXTRACTED_CHARGER_INFO.mkdir(parents=True, exist_ok=True)
    # extract writes into charger/info/{stamp}
    domain_path = extract_charger_info(key, stamp)
    raw = domain_path.read_bytes()
    n_rows = sum(1 for _ in domain_path.open(encoding="utf-8-sig")) - 1
    fetched_at = now.strftime("%Y-%m-%d %H:%M:%S")

    day_dir.mkdir(parents=True, exist_ok=True)
    stamped_daily = day_dir / f"daegu_charger_info_{stamp}.csv"
    stamped_daily.write_bytes(raw)
    day_latest.write_bytes(raw)

    rolling = EXTRACTED_CHARGER_INFO / "daegu_charger_info_latest.csv"
    rolling.write_bytes(raw)

    _append_index(
        export_date=export_date,
        path=stamped_daily,
        rows=n_rows,
        fetched_at=fetched_at,
    )

    header = domain_path.read_text(encoding="utf-8-sig").splitlines()[0]
    k12 = _k12_vs_previous(day_latest)
    meta = {
        "ok": True,
        "skipped": False,
        "export_date": export_date,
        "stamp": stamp,
        "source": SOURCE,
        "params": {"zcode": "27", "numOfRows": 999},
        "rows": n_rows,
        "statIds": len(_stat_ids(day_latest)),
        "has_limitYn": "limitYn" in header.split(","),
        "files": {
            "daily_stamped": str(stamped_daily.relative_to(REPO)).replace("\\", "/"),
            "daily_latest": str(day_latest.relative_to(REPO)).replace("\\", "/"),
            "domain_stamped": str(domain_path.relative_to(REPO)).replace("\\", "/"),
            "domain_rolling_latest": str(rolling.relative_to(REPO)).replace("\\", "/"),
        },
        "k12": k12,
        "note": "full API columns; D1 prefers CSVs with limitYn. service_latest is DQ output - not overwritten here.",
    }
    meta_path = day_dir / "info_dump_meta.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    # Windows cp949 consoles choke on some unicode; keep file UTF-8, stdout ASCII-safe
    print(json.dumps(meta, ensure_ascii=True, indent=2))
    return meta


def main() -> int:
    ap = argparse.ArgumentParser(description="Daily fixed-condition charger info dump")
    ap.add_argument("--force", action="store_true", help="re-fetch even if today's latest exists")
    args = ap.parse_args()
    run(force=args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
