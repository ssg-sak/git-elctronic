"""Daily usage EDA — auxiliary features only (NOT ETA targets)."""
from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd

from .paths import (
    HISTORY_FEAT,
    OUT_FIGURES,
    OUT_JSON,
    OUT_TABLES,
    USAGE_CSV,
    USAGE_JOIN,
    ensure_out,
)


def run_usage_eda() -> dict[str, Any]:
    ensure_out()
    if not USAGE_CSV.exists():
        return {"ok": False, "error": "usage csv missing"}

    df = None
    enc_used = None
    for enc in ("cp949", "utf-8-sig", "utf-8"):
        try:
            df = pd.read_csv(USAGE_CSV, encoding=enc)
            enc_used = enc
            break
        except Exception:
            continue
    assert df is not None

    # actual columns from file
    col_date = "일자"
    col_sid = "충전소아이디"
    col_name = "충전소명칭"
    col_cid = "충전기아이디"
    col_type = "충전기타입"
    col_sess = "사용횟수"
    col_kwh = "충전량"

    df[col_date] = pd.to_datetime(df[col_date], errors="coerce")
    df[col_sess] = pd.to_numeric(df[col_sess], errors="coerce")
    df[col_kwh] = pd.to_numeric(df[col_kwh], errors="coerce")
    df = df.dropna(subset=[col_date])
    df["weekday"] = df[col_date].dt.weekday
    df["is_weekend"] = df["weekday"] >= 5
    df["month"] = df[col_date].dt.month
    df["year"] = df[col_date].dt.year

    y2025 = df[(df[col_date] >= "2025-01-01") & (df[col_date] < "2026-01-01")]

    daily = df.groupby(col_date, as_index=False).agg(
        sessions=(col_sess, "sum"),
        kwh=(col_kwh, "sum"),
        chargers=(col_cid, "nunique"),
        stations=(col_sid, "nunique"),
    )
    daily["sessions_ma7"] = daily["sessions"].rolling(7, min_periods=1).mean()
    daily["sessions_ma28"] = daily["sessions"].rolling(28, min_periods=1).mean()

    # zero-use vs missing day: data is charger×day sparse — missing day ≠ zero
    # Approximate: for each charger, days present with sessions==0 vs absent
    charger_days = df.groupby([col_sid, col_cid]).agg(
        n_days=(col_date, "nunique"),
        zero_days=(col_sess, lambda s: int((s.fillna(0) == 0).sum())),
        mean_sessions=(col_sess, "mean"),
        mean_kwh=(col_kwh, "mean"),
    )
    span_days = (df[col_date].max() - df[col_date].min()).days + 1
    # cannot prove calendar zero without dense panel — flag as limited
    missing_vs_zero = {
        "can_distinguish": False,
        "reason": (
            "File is sparse charger×day rows. Days without a row are indistinguishable "
            "from 'not reported'; rows with 사용횟수=0 are true zero-use for that day."
        ),
        "rows_with_zero_sessions": int((df[col_sess].fillna(0) == 0).sum()),
        "calendar_span_days": int(span_days),
        "distinct_dates_in_file": int(df[col_date].nunique()),
    }

    by_weekday = df.groupby("weekday")[col_sess].mean()
    by_month = df.groupby("month")[col_sess].mean()
    by_type = df.groupby(col_type).agg(
        sessions_mean=(col_sess, "mean"),
        kwh_mean=(col_kwh, "mean"),
        rows=(col_sess, "size"),
    )

    sess = df[col_sess]
    kwh = df[col_kwh]
    per_session = (kwh / sess.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan)

    # station ranking
    st_rank = (
        df.groupby([col_sid, col_name])[col_sess]
        .sum()
        .sort_values(ascending=False)
        .reset_index()
    )
    st_rank["rank"] = np.arange(1, len(st_rank) + 1)
    st_rank.head(50).to_csv(OUT_TABLES / "usage_station_rank_top50.csv", index=False, encoding="utf-8-sig")

    # ID match to EvCharger
    match = {}
    if USAGE_JOIN.exists():
        j = pd.read_csv(USAGE_JOIN, dtype=str)
        match = {
            "join_rows": int(len(j)),
            "matched": int(j["matched"].astype(str).str.lower().isin({"true", "1", "yes", "True"}).sum())
            if "matched" in j.columns
            else None,
            "columns": list(j.columns),
        }

    # Feature feasibility checklist
    feat_ok = {
        "daily_avg_sessions": True,
        "weekday_avg_sessions": True,
        "weekend_avg_sessions": True,
        "rolling_7d_sessions": True,
        "rolling_28d_sessions": True,
        "usage_volatility": True,
        "zero_use_rate": "partial — only among reported days",
        "avg_kwh_per_session": True,
        "historical_usage_index": True,
    }
    # existing history features file
    existing = None
    if HISTORY_FEAT.exists():
        hf = pd.read_csv(HISTORY_FEAT, nrows=3)
        existing = {"path": str(HISTORY_FEAT).replace("\\", "/"), "columns": list(hf.columns), "rows": sum(1 for _ in open(HISTORY_FEAT, encoding="utf-8")) - 1}

    # build station-day for volatility example
    st_day = df.groupby([col_sid, col_date], as_index=False)[col_sess].sum()
    vol = st_day.groupby(col_sid)[col_sess].std()

    daily.to_csv(OUT_TABLES / "usage_daily_fleet.csv", index=False, encoding="utf-8-sig")
    by_weekday.rename("mean_sessions").reset_index().to_csv(
        OUT_TABLES / "usage_by_weekday.csv", index=False, encoding="utf-8-sig"
    )
    by_type.reset_index().to_csv(OUT_TABLES / "usage_by_charger_type.csv", index=False, encoding="utf-8-sig")

    result = {
        "ok": True,
        "encoding": enc_used,
        "rows": int(len(df)),
        "rows_2025": int(len(y2025)),
        "date_min": str(df[col_date].min().date()),
        "date_max": str(df[col_date].max().date()),
        "n_stations": int(df[col_sid].nunique()),
        "n_chargers": int(df.groupby([col_sid, col_cid]).ngroups),
        "daily_avg_sessions_fleet": float(daily["sessions"].mean()),
        "weekday_mean_sessions": {int(k): float(v) for k, v in by_weekday.items()},
        "weekend_vs_weekday_mean_row": {
            "weekday": float(df.loc[~df["is_weekend"], col_sess].mean()),
            "weekend": float(df.loc[df["is_weekend"], col_sess].mean()),
        },
        "by_type": by_type.reset_index().to_dict(orient="records"),
        "corr_sessions_kwh": float(df[[col_sess, col_kwh]].corr().iloc[0, 1]),
        "avg_kwh_per_session_median": float(per_session.median()) if per_session.notna().any() else None,
        "usage_volatility_station_median": float(vol.median()) if len(vol) else None,
        "missing_vs_zero": missing_vs_zero,
        "statId_match": match,
        "auxiliary_features_feasible": feat_ok,
        "existing_history_features": existing,
        "role_verdict": (
            "USEFUL as historical congestion auxiliary features after spatial ID join. "
            "NOT valid as ETA-at-arrival availability target (daily grain, no intraday occupancy)."
        ),
        "eta_target_forbidden": True,
    }

    try:
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(10, 4))
        ax.plot(daily[col_date], daily["sessions"], lw=0.8, alpha=0.5, label="daily")
        ax.plot(daily[col_date], daily["sessions_ma7"], lw=1.5, label="MA7")
        ax.plot(daily[col_date], daily["sessions_ma28"], lw=1.5, label="MA28")
        ax.legend()
        ax.set_title("Fleet daily sessions (usage) — auxiliary only")
        fig.tight_layout()
        fig.savefig(OUT_FIGURES / "usage_daily_sessions.png", dpi=120)
        plt.close(fig)

        fig, ax = plt.subplots(figsize=(6, 4))
        ax.bar(by_weekday.index, by_weekday.values, color="#2c5f6e")
        ax.set_xlabel("weekday (0=Mon)")
        ax.set_ylabel("mean sessions / row")
        ax.set_title("Usage by weekday")
        fig.tight_layout()
        fig.savefig(OUT_FIGURES / "usage_by_weekday.png", dpi=120)
        plt.close(fig)
    except Exception as exc:  # noqa: BLE001
        result["figure_error"] = str(exc)

    (OUT_JSON / "usage_eda.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    return result
