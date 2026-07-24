"""Periodic UTIC incident extract + spatial join (separate from status loop).

Default: every 15 minutes → extract_utic_incident → join_utic_incident.
Optional --rebuild-d1 runs build_d1_snapshot after join (heavier).
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
EXTRACT = Path(__file__).resolve().parents[1] / "extract" / "extract_utic_incident.py"
JOIN = Path(__file__).resolve().parents[1] / "extract" / "join_utic_incident.py"
D1 = (
    REPO
    / "apps/data-pipeline/evaluation/personal/experiments"
    / "SANDBOX_20260716_preprocess_pipeline"
    / "src/preprocessing/build_d1_snapshot.py"
)


def _ensure_utf8_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _run(script: Path) -> dict:
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    payload: dict = {
        "script": script.name,
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


def tick(*, rebuild_d1: bool) -> dict:
    steps = [_run(EXTRACT), _run(JOIN)]
    if rebuild_d1:
        steps.append(_run(D1))
    ok = all(s.get("ok") for s in steps)
    return {"ok": ok, "steps": steps}


def main() -> int:
    _ensure_utf8_stdout()
    parser = argparse.ArgumentParser(description="UTIC incident loop (SANDBOX-safe paths)")
    parser.add_argument("--interval-minutes", type=int, default=15)
    parser.add_argument("--max-runs", type=int, default=0, help="0 = infinite")
    parser.add_argument(
        "--rebuild-d1",
        action="store_true",
        help="Also rebuild D1 snapshot each tick (slow)",
    )
    parser.add_argument("--once", action="store_true", help="Single tick then exit")
    args = parser.parse_args()

    print(
        json.dumps(
            {
                "mode": "loop2",
                "interval_minutes": args.interval_minutes,
                "rebuild_d1": args.rebuild_d1,
                "note": "independent from EvCharger status loop; uses UTIC_API_KEY",
                "attribution": "경찰청 도시교통정보센터(UTIC)",
            },
            ensure_ascii=False,
        ),
        flush=True,
    )

    runs = 0
    try:
        while True:
            result = tick(rebuild_d1=args.rebuild_d1)
            print(json.dumps(result, ensure_ascii=False, default=str), flush=True)
            runs += 1
            if args.once or (args.max_runs and runs >= args.max_runs):
                break
            time.sleep(max(args.interval_minutes, 1) * 60)
    except KeyboardInterrupt:
        print(json.dumps({"stopped": True, "runs": runs}, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
