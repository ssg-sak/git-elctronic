"""Promote SANDBOX status panel report PNGs to official team-share pack."""
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[5]
KST = ZoneInfo("Asia/Seoul")
SRC = (
    REPO
    / "apps/data-pipeline/evaluation/personal/experiments"
    / "SANDBOX_20260717_status_periodic_collection/reports"
)
SHARE = REPO / "docs" / "팀공유"


def main() -> int:
    stamp = datetime.now(KST).strftime("%Y%m%d")
    out = SHARE / f"상태수집_패널차트_{stamp}"
    fig = out / "figures"
    fig.mkdir(parents=True, exist_ok=True)

    pngs = sorted(SRC.glob("*.png"))
    if not pngs:
        raise SystemExit(f"No PNGs in {SRC}")

    copied: list[str] = []
    for p in pngs:
        shutil.copy2(p, fig / p.name)
        copied.append(p.name)

    readme = "\n".join(
        [
            f"# 상태수집 패널차트 — {stamp} 갱신",
            "",
            "SANDBOX_20260717 status 주기수집 리포트 PNG를 **공식 팀공유 시각자료**로 승격한 팩입니다.",
            "",
            "| 항목 | 값 |",
            "|---|---:|",
            f"| 그림 수 | {len(copied)} |",
            f"| 원천 | `.../SANDBOX_20260717_status_periodic_collection/reports/` |",
            f"| 생성 | {datetime.now(KST).isoformat(timespec='seconds')} |",
            "",
            "## figures/",
            "",
            *[f"- `{n}`" for n in copied],
            "",
            "편향 비교·패널 가용률·관측 히스토그램·데이터 가치 요약(`status_data_value_*.png`)·대시보드를 포함합니다.",
            "",
            f"```\nDA① | status panel charts | {stamp}\n```",
            "",
        ]
    )
    (out / "README.md").write_text(readme, encoding="utf-8")
    (out / "pack_meta.json").write_text(
        json.dumps(
            {
                "stamp": stamp,
                "source": str(SRC.relative_to(REPO)).replace("\\", "/"),
                "n_png": len(copied),
                "files": copied,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps({"out": str(out), "n": len(copied)}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
