"""Copy latest snapshot_all figures+data into docs/팀공유/시간대_가용률_<stamp>/."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import shutil

REPO = Path(__file__).resolve().parents[5]
KST = ZoneInfo("Asia/Seoul")
DATA_NAMES = [
    "availability_by_hour_union.csv",
    "availability_by_hour_public_vs_residential.csv",
    "availability_tod.csv",
    "reliability_checks.json",
    "summary.json",
]


def main() -> None:
    stamp = datetime.now(KST).strftime("%Y%m%d")
    srcs = sorted(
        [
            p
            for p in (REPO / "docs/data/analysis").glob("snapshot_all_*")
            if p.is_dir() and (p / "figures").is_dir()
        ],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not srcs:
        raise SystemExit("no snapshot_all_* directory with figures/")
    src = srcs[0]
    share = REPO / "docs" / "팀공유" / f"시간대_가용률_{stamp}"
    (share / "figures").mkdir(parents=True, exist_ok=True)
    (share / "data").mkdir(parents=True, exist_ok=True)

    figs = 0
    for p in (src / "figures").glob("*.png"):
        shutil.copy2(p, share / "figures" / p.name)
        figs += 1

    data = 0
    for name in DATA_NAMES:
        sp = src / name
        if sp.exists():
            shutil.copy2(sp, share / "data" / name)
            data += 1

    summary = src / "summary.json"
    snaps = last = ""
    if summary.exists():
        meta = json.loads(summary.read_text(encoding="utf-8"))
        snaps = (
            meta.get("unique_snapshots")
            or meta.get("snapshots")
            or meta.get("n_snapshots")
            or ""
        )
        last = meta.get("last_ts") or meta.get("last") or ""
    (share / "README.md").write_text(
        f"# hourly avail {stamp}\n\nsnaps={snaps} last={last}\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "ok": True,
                "src": str(src.relative_to(REPO)).replace("\\", "/"),
                "share": str(share.relative_to(REPO)).replace("\\", "/"),
                "figures": figs,
                "data_files": data,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
