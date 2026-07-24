"""Run all DA➀ viability (GO/NO-GO) tests and write a combined summary.

  python apps/data-pipeline/evaluation/viability_tests/run_all_viability.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent


def _repo_root() -> Path:
    for p in [HERE, *HERE.parents]:
        if (p / "AGENTS.md").exists() and (p / "apps" / "data-pipeline").exists():
            return p
    raise RuntimeError("cannot locate repo root from viability_tests")


REPO = _repo_root()
OUT = REPO / "apps/data-pipeline/evaluation/results/go_nogo"
KST = ZoneInfo("Asia/Seoul")

TESTS = [
    ("status", HERE / "test_status_go_nogo_viability.py", "status_viability_latest.json"),
    ("utic", HERE / "test_utic_incident_go_nogo_viability.py", "utic_viability_latest.json"),
]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    results = []
    worst = 0
    for name, script, json_name in TESTS:
        print(f"\n===== RUN {name} =====\n", flush=True)
        proc = subprocess.run([sys.executable, str(script)], cwd=str(REPO))
        code = int(proc.returncode)
        worst = max(worst, code)
        payload = {}
        jp = OUT / json_name
        if jp.exists():
            payload = json.loads(jp.read_text(encoding="utf-8"))
        results.append(
            {
                "name": name,
                "exit_code": code,
                "overall": payload.get("overall"),
                "kill": payload.get("kill_project")
                if name == "status"
                else payload.get("kill_utic_track"),
                "keep": payload.get("project_keep")
                if name == "status"
                else payload.get("project_keep_utic_track"),
                "plain": payload.get("plain_korean"),
                "report_md": str(OUT / json_name.replace(".json", ".md")),
            }
        )

    summary = {
        "generated_at": datetime.now(tz=KST).isoformat(),
        "results": results,
        "any_kill": any(r.get("kill") for r in results),
        "all_keep": all(r.get("keep") for r in results),
    }
    (OUT / "viability_all_latest.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        "# DA➀ 타당성 테스트 종합",
        "",
        f"| 생성 | `{summary['generated_at']}` |",
        f"| 전부 유지 | **{summary['all_keep']}** |",
        f"| 폐기/트랙실패 있음 | **{summary['any_kill']}** |",
        "",
        "| 테스트 | overall | keep | kill | exit |",
        "|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r['name']} | {r['overall']} | {r['keep']} | {r['kill']} | {r['exit_code']} |"
        )
    lines.append("")
    for r in results:
        lines.append(f"## {r['name']}")
        lines.append("")
        lines.append(r.get("plain") or "")
        lines.append("")
        lines.append(f"상세: `{r['report_md']}`")
        lines.append("")
    lines += [
        "```bash",
        "python apps/data-pipeline/evaluation/viability_tests/run_all_viability.py",
        "```",
        "",
    ]
    md = OUT / "viability_all_latest.md"
    md.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"summary_md": str(md), **{k: summary[k] for k in ("any_kill", "all_keep")}}, ensure_ascii=False, indent=2))
    return 2 if summary["any_kill"] else 0


if __name__ == "__main__":
    sys.exit(main())
