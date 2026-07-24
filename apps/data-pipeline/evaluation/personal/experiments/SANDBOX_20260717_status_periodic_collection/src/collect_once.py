"""One-shot status snapshot into SANDBOX (never touches extracted/)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent
sys.path.insert(0, str(SRC))

from collect_status import collect_snapshot  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect one getChargerStatus snapshot into SANDBOX")
    parser.add_argument(
        "--period-minutes",
        type=int,
        default=20,
        help="EvCharger API period: status changed within last N minutes (not our poll interval)",
    )
    args = parser.parse_args()
    result = collect_snapshot(period_minutes=args.period_minutes)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("skipped"):
        return 2
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
