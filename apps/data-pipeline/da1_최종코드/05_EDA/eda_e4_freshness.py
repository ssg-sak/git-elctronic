"""E4: availability by status freshness (age / reliability grade).

Uses D1 station_feature_snapshot_latest.
Does not score stations (AI·data ②).
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[4]
EVAL = Path(__file__).resolve().parents[1]
DATASETS = EVAL / "results" / "datasets"
OUT = EVAL / "results" / "eda"
KST = ZoneInfo("Asia/Seoul")


def age_bucket(m) -> str:
    if m != m or m is None:  # NaN
        return "UNOBSERVED"
    m = float(m)
    if m <= 5:
        return "<=5min_HIGH"
    if m <= 15:
        return "5-15min_NORMAL"
    return ">15min_CHECK"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    d1_path = DATASETS / "station_feature_snapshot_latest.csv"
    d1 = pd.read_csv(d1_path)
    d1["age"] = pd.to_numeric(d1["status_age_minutes"], errors="coerce")
    d1["avail"] = pd.to_numeric(d1["availability_ratio_observed"], errors="coerce")
    d1["unobs"] = pd.to_numeric(d1["unobserved_rate"], errors="coerce")
    d1["confirmed"] = d1["has_confirmed_available"].astype(str).str.lower().isin(
        ["true", "1"]
    )
    d1["age_bucket"] = d1["age"].map(age_bucket)
    # if all chargers unobserved, age is null → UNOBSERVED
    d1.loc[d1["age"].isna(), "age_bucket"] = "UNOBSERVED"

    order = ["<=5min_HIGH", "5-15min_NORMAL", ">15min_CHECK", "UNOBSERVED"]
    rows = []
    for b in order:
        part = d1[d1["age_bucket"] == b]
        a = part["avail"].dropna()
        rows.append(
            {
                "age_bucket": b,
                "stations": len(part),
                "share_pct": round(100.0 * len(part) / max(len(d1), 1), 2),
                "age_median_min": round(float(part["age"].median()), 1)
                if part["age"].notna().any()
                else None,
                "confirmed_rate": round(float(part["confirmed"].mean()), 4)
                if len(part)
                else None,
                "avail_mean": round(float(a.mean()), 4) if len(a) else None,
                "unobserved_rate_mean": round(float(part["unobs"].mean()), 4)
                if len(part)
                else None,
            }
        )
    out = pd.DataFrame(rows)
    csv_path = OUT / "e4_availability_by_freshness.csv"
    out.to_csv(csv_path, index=False, encoding="utf-8-sig")

    grade = (
        d1.groupby(d1["reliability_grade"].fillna("NA"), dropna=False)
        .agg(
            stations=("statId", "size"),
            confirmed_rate=("confirmed", "mean"),
            avail_mean=("avail", "mean"),
            age_median=("age", "median"),
        )
        .reset_index()
        .rename(columns={"reliability_grade": "reliability_grade"})
    )
    grade["confirmed_rate"] = grade["confirmed_rate"].round(4)
    grade["avail_mean"] = grade["avail_mean"].round(4)
    grade["age_median"] = grade["age_median"].round(1)
    grade_path = OUT / "e4_availability_by_reliability_grade.csv"
    grade.to_csv(grade_path, index=False, encoding="utf-8-sig")

    meta = {
        "analysis": "E4_freshness_x_availability",
        "generated_at": datetime.now(KST).isoformat(),
        "d1_as_of": str(d1["as_of_ts"].iloc[0]) if "as_of_ts" in d1.columns else None,
        "stations": int(len(d1)),
        "high_count": int((d1["age_bucket"] == "<=5min_HIGH").sum()),
        "normal_count": int((d1["age_bucket"] == "5-15min_NORMAL").sum()),
        "check_count": int((d1["age_bucket"] == ">15min_CHECK").sum()),
        "unobserved_count": int((d1["age_bucket"] == "UNOBSERVED").sum()),
        "csv_bucket": str(csv_path.resolve().relative_to(REPO_ROOT)).replace("\\", "/"),
        "csv_grade": str(grade_path.resolve().relative_to(REPO_ROOT)).replace("\\", "/"),
        "note": (
            "D1 as-of uses newest status per charger; many stations only have older "
            "observations → CHECK_REQUIRED dominates. Correlation ≠ causation."
        ),
    }
    (OUT / "e4_availability_by_freshness_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    print(out.to_string(index=False))
    print(grade.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
