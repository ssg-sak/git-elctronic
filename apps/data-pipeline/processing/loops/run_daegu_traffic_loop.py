"""Periodic Daegu ITS traffic extract (linkspeed + dgincident).

Default: every 15 minutes → extract_daegu_traffic.
Independent from EvCharger status loop and UTIC loop (uses DATA_GO_KR_KEY).
Each tick = 2 API calls (linkspeed + dgincident) against the shared daily quota.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import sys
from pathlib import Path
_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))
from _bootstrap import ensure_paths

REPO = ensure_paths()
EXTRACT = Path(__file__).resolve().parents[1] / "extract" / "extract_daegu_traffic.py"


def _ensure_utf8_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _run_extract() -> dict:
    proc = subprocess.run(
        [sys.executable, str(EXTRACT)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    payload: dict = {
        "script": EXTRACT.name,
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
    }
    if out:
        try:
            payload["result"] = json.loads(out)
        except json.JSONDecodeError:
            start = out.find("{")
            end = out.rfind("}")
            if start >= 0 and end > start:
                try:
                    payload["result"] = json.loads(out[start : end + 1])
                except json.JSONDecodeError:
                    payload["stdout_tail"] = out[-500:]
            else:
                payload["stdout_tail"] = out[-500:]
    if err and proc.returncode != 0:
        payload["stderr_tail"] = err[-500:]
    return payload


def tick() -> dict:
    step = _run_extract()
    result = step.get("result") or {}
    return {
        "ok": step.get("ok", False),
        "linkspeed_rows": (result.get("linkspeed") or {}).get("rows"),
        "incident_rows": (result.get("incident") or {}).get("rows"),
        "fetched_at": result.get("fetched_at"),
        "speed_kph_mean": (result.get("linkspeed") or {}).get("speed_kph_mean"),
        "step": step,
    }


def main() -> int:
    _ensure_utf8_stdout()
    parser = argparse.ArgumentParser(description="Daegu ITS traffic loop (linkspeed + dgincident)")
    parser.add_argument("--interval-minutes", type=int, default=15)
    parser.add_argument("--max-runs", type=int, default=0, help="0 = infinite")
    parser.add_argument("--once", action="store_true", help="Single tick then exit")
    args = parser.parse_args()

    print(
        json.dumps(
            {
                "mode": "loop3",
                "interval_minutes": args.interval_minutes,
                "api_calls_per_tick": 2,
                "note": "independent from status/UTIC loops; uses DATA_GO_KR_KEY",
                "attribution": "대구광역시 교통정보(ATMS) · 공공데이터포털",
            },
            ensure_ascii=False,
        ),
        flush=True,
    )

    runs = 0
    last_ok = False
    try:
        while True:
            result = tick()
            last_ok = bool(result.get("ok"))
            print(json.dumps(result, ensure_ascii=False, default=str), flush=True)
            runs += 1
            if args.once or (args.max_runs and runs >= args.max_runs):
                break
            time.sleep(max(args.interval_minutes, 1) * 60)
    except KeyboardInterrupt:
        print(json.dumps({"stopped": True, "runs": runs}, ensure_ascii=False), flush=True)
    return 0 if last_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
