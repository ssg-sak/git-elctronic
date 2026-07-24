"""Print collection run summary from index.csv and daily quota."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

SANDBOX_ROOT = Path(__file__).resolve().parents[1]
INDEX_CSV = SANDBOX_ROOT / "data" / "index.csv"
QUOTA_JSON = SANDBOX_ROOT / "data" / "logs" / "daily_quota.json"


def main() -> int:
    if not INDEX_CSV.exists():
        print(json.dumps({"ok": False, "error": "index.csv missing"}, ensure_ascii=False))
        return 1

    idx = pd.read_csv(INDEX_CSV)
    idx["fetchedAt"] = pd.to_datetime(idx["fetchedAt"], errors="coerce")

    summary = {
        "ok": True,
        "snapshots": int(len(idx)),
        "total_rows": int(idx["rows"].sum()),
        "total_api_calls": int(idx["api_calls"].sum()),
        "rows_mean": round(float(idx["rows"].mean()), 1),
        "rows_min": int(idx["rows"].min()),
        "rows_max": int(idx["rows"].max()),
        "period_values": sorted(idx["period_minutes"].dropna().unique().tolist()),
        "first_fetched": str(idx["fetchedAt"].min()),
        "last_fetched": str(idx["fetchedAt"].max()),
    }

    if QUOTA_JSON.exists():
        summary["daily_quota"] = json.loads(QUOTA_JSON.read_text(encoding="utf-8"))

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("\n--- recent snapshots ---")
    print(
        idx.sort_values("fetchedAt", ascending=False)
        .head(10)[["snapshotId", "rows", "api_calls", "period_minutes", "fetchedAt"]]
        .to_string(index=False)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
