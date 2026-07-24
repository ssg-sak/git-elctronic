"""Loop collector: snapshot every N minutes into SANDBOX only."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

SRC = Path(__file__).resolve().parent
SANDBOX_ROOT = SRC.parent
REPO_ROOT = SANDBOX_ROOT.parents[5]
COLLECTION_DIR = REPO_ROOT / "apps" / "data-pipeline" / "collection"
KST = ZoneInfo("Asia/Seoul")

sys.path.insert(0, str(SRC))
sys.path.insert(0, str(COLLECTION_DIR))

from collect_status import collect_snapshot  # noqa: E402
from daily_checkpoint import ensure_previous_day_checkpoint  # noqa: E402

import daily_exports  # noqa: E402


def _ensure_daily_info_export() -> dict[str, object]:
    """Collect info once per day and write docs/data/extracted/daily/YYYY-MM-DD/."""
    if daily_exports.info_export_exists_for_today():
        return {"event": "daily_info", "skipped": True, "reason": "already_exported_today"}

    result: dict[str, object] = {"event": "daily_info", "skipped": False}
    try:
        proc = subprocess.run(
            [sys.executable, str(COLLECTION_DIR / "ev_charger_info.py")],
            cwd=str(COLLECTION_DIR),
            capture_output=True,
            text=True,
            check=False,
        )
        result["exit_code"] = proc.returncode
        if proc.stdout.strip():
            result["stdout_tail"] = proc.stdout.strip()[-500:]
        if proc.returncode != 0:
            result["ok"] = False
            result["stderr_tail"] = (proc.stderr or "").strip()[-500:]
            return result
        today = datetime.now(tz=KST).date().isoformat()
        day_dir = daily_exports.DAILY_ROOT / today
        csv_files = sorted(day_dir.glob("daegu_charger_info_*.csv"))
        result["ok"] = True
        result["path"] = str(csv_files[-1]) if csv_files else None
        return result
    except Exception as exc:  # info export must never stop status loop
        result["ok"] = False
        result["error"] = str(exc)
        return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Periodic status snapshots (SANDBOX only)")
    parser.add_argument("--interval-minutes", type=int, default=5, help="Our poll interval (minutes between API calls)")
    parser.add_argument("--period-minutes", type=int, default=10, help="EvCharger API: status changed within last N minutes (max 10)")
    parser.add_argument("--max-runs", type=int, default=0, help="0 = infinite until Ctrl+C")
    args = parser.parse_args()

    runs = 0
    last_info_date = None
    print(
        json.dumps(
            {
                "mode": "loop1",
                "interval_minutes": args.interval_minutes,
                "period_minutes": args.period_minutes,
                "interval_note": "our scheduler: how often we call API",
                "period_note": "API param: return chargers with status updated in last N minutes",
                "note": "writes docs/data/loops/loop1/; never docs/data/extracted/",
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    try:
        while True:
            result = collect_snapshot(period_minutes=args.period_minutes)
            print(json.dumps(result, ensure_ascii=False), flush=True)
            if result.get("ok") and not result.get("skipped"):
                today = datetime.now(tz=KST).date()
                if last_info_date != today:
                    info_result = _ensure_daily_info_export()
                    print(json.dumps(info_result, ensure_ascii=False, default=str), flush=True)
                    last_info_date = today
                try:
                    checkpoint = ensure_previous_day_checkpoint()
                    if checkpoint.get("generated"):
                        print(
                            json.dumps(
                                {"event": "daily_checkpoint", **checkpoint},
                                ensure_ascii=False,
                                default=str,
                            ),
                            flush=True,
                        )
                except Exception as exc:  # checkpoint must never stop collection
                    print(
                        json.dumps(
                            {
                                "event": "daily_checkpoint_error",
                                "error": str(exc),
                            },
                            ensure_ascii=False,
                        ),
                        flush=True,
                    )
            runs += 1
            if args.max_runs and runs >= args.max_runs:
                break
            time.sleep(max(args.interval_minutes, 1) * 60)
    except KeyboardInterrupt:
        print(json.dumps({"stopped": True, "runs": runs}, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
