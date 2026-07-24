"""E2: day-of-week availability from D2 panel (PROVISIONAL).

Few calendar days only — do not treat as stable weekday rules.
Does not compute recommendation scores (AI·data ②).
Plan: docs/보고/EDA_계획_상태패널.md
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

DOW_KO = {0: "월", 1: "화", 2: "수", 3: "목", 4: "금", 5: "토", 6: "일"}
MIN_TIMESTAMPS = 2
MIN_PANEL_ROWS = 3000


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    panel_path = DATASETS / "station_feature_panel_latest.parquet"
    if not panel_path.exists():
        panel_path = DATASETS / "station_feature_panel_latest.csv"
    df = (
        pd.read_parquet(panel_path)
        if panel_path.suffix == ".parquet"
        else pd.read_csv(panel_path)
    )
    df["panel_ts"] = pd.to_datetime(df["panel_ts"])
    df["dow"] = df["panel_ts"].dt.dayofweek
    df["is_weekend"] = df["dow"] >= 5
    df["avail"] = pd.to_numeric(df["availability_ratio_observed"], errors="coerce")
    df["confirmed"] = df["has_confirmed_available"].astype(str).str.lower().isin(
        ["true", "1"]
    )
    usable = pd.to_numeric(df["usable_known"], errors="coerce")
    in_use = pd.to_numeric(df["in_use_count"], errors="coerce")
    df["in_use_rate"] = in_use / usable.replace(0, pd.NA)

    calendar_days = sorted({d.isoformat() for d in df["panel_ts"].dt.date.unique()})

    rows = []
    for dow in range(7):
        part = df[df["dow"] == dow]
        name = DOW_KO[dow]
        if part.empty:
            rows.append(
                {
                    "dow": dow,
                    "dow_ko": name,
                    "is_weekend": dow >= 5,
                    "analyzable": False,
                    "provisional": True,
                    "panel_rows": 0,
                    "n_timestamps": 0,
                    "n_calendar_dates": 0,
                    "n_stations": 0,
                    "avail_mean": None,
                    "avail_median": None,
                    "confirmed_rate": None,
                    "in_use_rate_mean": None,
                    "exclude_reason": "no_data_in_panel",
                }
            )
            continue
        a = part["avail"].dropna()
        n_ts = int(part["panel_ts"].nunique())
        n_rows = len(part)
        n_dates = int(part["panel_ts"].dt.date.nunique())
        analyzable = n_ts >= MIN_TIMESTAMPS and n_rows >= MIN_PANEL_ROWS
        rows.append(
            {
                "dow": dow,
                "dow_ko": name,
                "is_weekend": dow >= 5,
                "analyzable": analyzable,
                "provisional": True,
                "panel_rows": n_rows,
                "n_timestamps": n_ts,
                "n_calendar_dates": n_dates,
                "n_stations": int(part["statId"].nunique()),
                "avail_mean": round(float(a.mean()), 4) if len(a) else None,
                "avail_median": round(float(a.median()), 4) if len(a) else None,
                "confirmed_rate": round(float(part["confirmed"].mean()), 4),
                "in_use_rate_mean": round(float(part["in_use_rate"].mean()), 4)
                if part["in_use_rate"].notna().any()
                else None,
                "exclude_reason": ""
                if analyzable
                else f"thin: timestamps<{MIN_TIMESTAMPS} or rows<{MIN_PANEL_ROWS}",
            }
        )
    out = pd.DataFrame(rows)
    csv_path = OUT / "e2_availability_by_dow.csv"
    out.to_csv(csv_path, index=False, encoding="utf-8-sig")

    ok = out[out["analyzable"]].copy()
    # weekday vs weekend among analyzable rows in raw panel
    wd = df.loc[~df["is_weekend"], "avail"].dropna()
    we = df.loc[df["is_weekend"], "avail"].dropna()

    meta = {
        "analysis": "E2_dow_availability",
        "provisional": True,
        "provisional_reason": (
            "Only a few calendar days; missing Tue–Thu entirely; "
            "do not treat as stable weekday rules"
        ),
        "generated_at": datetime.now(KST).isoformat(),
        "source": str(panel_path.resolve().relative_to(REPO_ROOT)).replace("\\", "/"),
        "calendar_dates": calendar_days,
        "panel_ts_min": str(df["panel_ts"].min()),
        "panel_ts_max": str(df["panel_ts"].max()),
        "days_with_data": ok["dow_ko"].tolist(),
        "days_missing": out.loc[out["panel_rows"] == 0, "dow_ko"].tolist(),
        "filter": {"min_timestamps": MIN_TIMESTAMPS, "min_panel_rows": MIN_PANEL_ROWS},
        "avail_mean_weekday_pooled": round(float(wd.mean()), 4) if len(wd) else None,
        "avail_mean_weekend_pooled": round(float(we.mean()), 4) if len(we) else None,
        "csv": str(csv_path.resolve().relative_to(REPO_ROOT)).replace("\\", "/"),
    }
    (OUT / "e2_availability_by_dow_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    print(out.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
