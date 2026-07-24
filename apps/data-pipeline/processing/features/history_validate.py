"""History quality checks (DATA_PART_WORK_GUIDE §4.4)."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

import sys
from pathlib import Path
_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))
from _bootstrap import ensure_paths

ensure_paths()

from features.status_standard import OFFICIAL_STATUSES

REQUIRED_COLUMNS = frozenset(
    {"observedAt", "stationId", "chargerId", "status"}
)


def validate_history(df: pd.DataFrame) -> dict:
    missing_columns = sorted(REQUIRED_COLUMNS - set(df.columns))
    if missing_columns:
        raise ValueError(f"필수 컬럼 누락: {missing_columns}")

    status = df["status"].astype(str).str.upper()
    invalid_status = ~status.isin(OFFICIAL_STATUSES)

    dup_cols = ["observedAt", "stationId", "chargerId", "status"]
    dup_cols = [c for c in dup_cols if c in df.columns]

    return {
        "rows": int(len(df)),
        "stations": int(df["stationId"].nunique()),
        "chargers": int(df.groupby(["stationId", "chargerId"]).ngroups),
        "observed_at_min": str(df["observedAt"].min()),
        "observed_at_max": str(df["observedAt"].max()),
        "duplicate_rows": int(df.duplicated().sum()),
        "duplicate_event_keys": int(df.duplicated(subset=dup_cols).sum()) if dup_cols else 0,
        "missing_values": {k: int(v) for k, v in df.isna().sum().to_dict().items()},
        "invalid_status_rows": int(invalid_status.sum()),
        "status_counts": status.value_counts().to_dict(),
    }


def save_quality_report(
    report: dict,
    path: str | Path,
    *,
    also_markdown: bool = True,
) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if also_markdown:
        md_path = path.with_suffix(".md")
        lines = [
            "# 목 상태 이력 품질 리포트",
            "",
            f"| 항목 | 값 |",
            f"|---|---|",
        ]
        for k, v in report.items():
            if isinstance(v, dict):
                lines.append(f"| {k} | |")
                for sk, sv in v.items():
                    lines.append(f"| · {sk} | {sv} |")
            else:
                lines.append(f"| {k} | {v} |")
        md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
