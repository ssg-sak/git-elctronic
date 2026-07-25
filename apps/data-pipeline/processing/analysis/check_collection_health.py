"""Write a local freshness report for the collected dynamic data.

This check is read-only: it does not call an API or rebuild D1.

Usage (repo root):
  python apps/data-pipeline/processing/analysis/check_collection_health.py
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))
from _bootstrap import ensure_paths

REPO = ensure_paths()
from loop_paths import LOOP1_SNAPSHOTS, iter_loop3_csvs, iter_status_csvs  # noqa: E402

KST = ZoneInfo("Asia/Seoul")
STAMP = re.compile(r"(20\d{6})[_-]?(\d{6})")
OUT = REPO / "docs" / "data" / "quality" / "collection_health_latest.json"


def collected_at(path: Path) -> datetime | None:
    """Return timestamp embedded in a snapshot filename, when present."""
    match = STAMP.search(path.name)
    if not match:
        return None
    try:
        return datetime.strptime(
            f"{match.group(1)}{match.group(2)}", "%Y%m%d%H%M%S"
        ).replace(tzinfo=KST)
    except ValueError:
        return None


def newest(paths: list[Path]) -> tuple[Path | None, datetime | None]:
    dated = [(path, collected_at(path)) for path in paths]
    dated = [(path, ts) for path, ts in dated if ts is not None]
    if not dated:
        return None, None
    return max(dated, key=lambda item: item[1])


def source_check(name: str, paths: list[Path], max_age_minutes: int) -> dict[str, object]:
    latest_path, latest_at = newest(paths)
    now = datetime.now(KST)
    age_minutes = (
        round((now - latest_at).total_seconds() / 60, 1) if latest_at else None
    )
    return {
        "source": name,
        "file_count": len(paths),
        "latest_file": (
            str(latest_path.relative_to(REPO)).replace("\\", "/")
            if latest_path
            else None
        ),
        "latest_collected_at_kst": latest_at.isoformat() if latest_at else None,
        "age_minutes": age_minutes,
        "max_age_minutes": max_age_minutes,
        "status": (
            "PASS"
            if age_minutes is not None and age_minutes <= max_age_minutes
            else "STALE_OR_MISSING"
        ),
    }


def main() -> int:
    status = source_check(
        "EvCharger status (loop1)", list(iter_status_csvs(LOOP1_SNAPSHOTS)), 30
    )
    traffic = source_check("Daegu traffic (loop3)", list(iter_loop3_csvs()), 45)
    report = {
        "checked_at_kst": datetime.now(KST).isoformat(timespec="seconds"),
        "checks": [status, traffic],
        "overall": "PASS"
        if all(item["status"] == "PASS" for item in (status, traffic))
        else "CHECK_REQUIRED",
        "note": "Local-file freshness only. Run after Lightsail pull; this does not call APIs or rebuild D1.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"OUT {OUT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
