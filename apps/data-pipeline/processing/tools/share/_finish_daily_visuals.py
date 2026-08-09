"""Copy hourly figures + print D1 summary after daily update."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

REPO = Path(__file__).resolve().parents[5]
KST = ZoneInfo("Asia/Seoul")


def main() -> int:
    stamp = datetime.now(KST).strftime("%Y%m%d")
    src = REPO / "docs/data/analysis/snapshot_all_20260723"
    share = REPO / "docs" / "팀공유" / f"시간대_가용률_{stamp}"
    (share / "figures").mkdir(parents=True, exist_ok=True)
    (share / "data").mkdir(parents=True, exist_ok=True)
    n = 0
    for p in (src / "figures").glob("*.png"):
        (share / "figures" / p.name).write_bytes(p.read_bytes())
        n += 1
    for name in (
        "availability_by_hour_union.csv",
        "availability_by_hour_public_vs_residential.csv",
        "availability_tod.csv",
        "reliability_checks.json",
        "summary.json",
    ):
        sp = src / name
        if sp.exists():
            (share / "data" / name).write_bytes(sp.read_bytes())
    s = json.loads((src / "summary.json").read_text(encoding="utf-8"))
    (share / "README.md").write_text(
        f"# hourly avail {stamp}\n\nsnaps={s.get('unique_snapshots')} "
        f"last={s.get('last_ts')}\n",
        encoding="utf-8",
    )
    d1 = pd.read_csv(
        REPO
        / "apps/data-pipeline/evaluation/results/datasets/station_feature_snapshot_latest.csv",
        encoding="utf-8-sig",
        low_memory=False,
    )
    print("SHARE", share, "figs", n)
    print("as_of", d1["as_of_ts"].iloc[0])
    print(d1["observation_state"].value_counts().to_string())
    print(
        "confirmed_pct",
        round(float(d1["has_confirmed_available"].mean()) * 100, 1),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
