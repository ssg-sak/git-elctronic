"""ETA horizon target feasibility — observed-only labels (null ≠ 0)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .paths import OUT_FIGURES, OUT_JSON, OUT_TABLES, ensure_out

HORIZONS = (5, 10, 15, 30)
PRIMARY = 15
TOL_MINUTES = 7.5


def _build_targets(station_tick: pd.DataFrame, horizon: int, tol: float = TOL_MINUTES) -> pd.DataFrame:
    df = station_tick.copy()
    df["panel_time"] = pd.to_datetime(df["panel_time"])
    df = df.sort_values(["station_id", "panel_time"]).reset_index(drop=True)

    base = df[df["collection_success"]].copy()
    fut = df[df["collection_success"]][
        ["station_id", "panel_time", "available_observed", "usable_observed", "observed_chargers"]
    ].rename(
        columns={
            "panel_time": "fut_time",
            "available_observed": "fut_available_observed",
            "usable_observed": "fut_usable_observed",
            "observed_chargers": "fut_observed_chargers",
        }
    )

    base = base.copy()
    base["target_time"] = base["panel_time"] + pd.Timedelta(minutes=horizon)

    # merge_asof per station
    parts = []
    for sid, g in base.groupby("station_id", sort=False):
        g = g.sort_values("target_time")
        f = fut[fut["station_id"] == sid].sort_values("fut_time")
        if f.empty:
            gg = g.copy()
            gg["fut_time"] = pd.NaT
            gg["fut_available_observed"] = np.nan
            gg["fut_usable_observed"] = np.nan
            gg["fut_observed_chargers"] = np.nan
            parts.append(gg)
            continue
        m = pd.merge_asof(
            g,
            f.drop(columns=["station_id"]),
            left_on="target_time",
            right_on="fut_time",
            direction="nearest",
            tolerance=pd.Timedelta(minutes=tol),
        )
        parts.append(m)
    out = pd.concat(parts, ignore_index=True)

    labels = []
    reasons = []
    for r in out.itertuples():
        if pd.isna(r.fut_time):
            labels.append(None)
            reasons.append("no_tick_near_horizon")
        elif int(r.fut_observed_chargers or 0) <= 0:
            labels.append(None)
            reasons.append("horizon_tick_no_charger_observation")
        elif int(r.fut_usable_observed or 0) <= 0:
            labels.append(None)
            reasons.append("horizon_observed_but_no_usable_2_or_3")
        else:
            labels.append(1 if int(r.fut_available_observed) >= 1 else 0)
            reasons.append("ok")

    out["target_available"] = labels
    out["label_reason"] = reasons
    out["horizon_min"] = horizon
    out["date"] = out["panel_time"].dt.date.astype(str)
    out["hour"] = out["panel_time"].dt.hour
    return out[
        [
            "station_id",
            "panel_time",
            "horizon_min",
            "target_available",
            "label_reason",
            "available_observed",
            "observed_chargers",
            "date",
            "hour",
        ]
    ].rename(columns={"panel_time": "t", "available_observed": "available_observed_at_t", "observed_chargers": "observed_chargers_at_t"})


def run_eta_targets(station_tick_path: str | Path | None = None) -> dict[str, Any]:
    ensure_out()
    path = Path(station_tick_path) if station_tick_path else OUT_TABLES / "station_tick_panel.parquet"
    if not path.exists():
        alt = OUT_TABLES / "station_tick_panel.csv"
        if alt.exists():
            path = alt
        else:
            return {"ok": False, "error": f"missing {path}"}

    if path.suffix == ".parquet":
        st = pd.read_parquet(path)
    else:
        st = pd.read_csv(path)
    # keep stations that ever have observations
    obs_counts = st.groupby("station_id")["observed_chargers"].apply(lambda s: (s > 0).sum())
    keep = obs_counts[obs_counts >= 3].index
    st = st[st["station_id"].isin(keep)].copy()

    horizon_stats: dict[str, Any] = {}
    primary_df = None
    for h in HORIZONS:
        tg = _build_targets(st, h)
        labeled = tg["target_available"].notna()
        n_total = len(tg)
        n_lab = int(labeled.sum())
        y = tg.loc[labeled, "target_available"]
        pos = int((y == 1).sum()) if n_lab else 0
        neg = int((y == 0).sum()) if n_lab else 0
        stats = {
            "horizon_min": h,
            "candidate_rows": n_total,
            "labeled_rows": n_lab,
            "null_rows": n_total - n_lab,
            "coverage": n_lab / n_total if n_total else 0.0,
            "positive": pos,
            "negative": neg,
            "positive_rate": pos / n_lab if n_lab else None,
            "stations_with_label": int(tg.loc[labeled, "station_id"].nunique()) if n_lab else 0,
            "dates_with_label": int(tg.loc[labeled, "date"].nunique()) if n_lab else 0,
            "label_reason_counts": tg["label_reason"].value_counts().to_dict(),
        }
        horizon_stats[str(h)] = stats
        tg.to_csv(OUT_TABLES / f"eta_targets_{h}m.csv", index=False, encoding="utf-8-sig")
        if h == PRIMARY:
            primary_df = tg

    assert primary_df is not None
    lab = primary_df[primary_df["target_available"].notna()].copy()
    by_station = lab.groupby("station_id").size().describe().to_dict() if len(lab) else {}
    by_date = lab.groupby("date").size() if len(lab) else pd.Series(dtype=int)
    by_hour = lab.groupby("hour").size() if len(lab) else pd.Series(dtype=int)

    if len(by_date):
        by_date.rename("n").reset_index().to_csv(
            OUT_TABLES / "eta15_labels_by_date.csv", index=False, encoding="utf-8-sig"
        )
    if len(by_hour):
        by_hour.rename("n").reset_index().to_csv(
            OUT_TABLES / "eta15_labels_by_hour.csv", index=False, encoding="utf-8-sig"
        )

    if len(lab) and lab["date"].nunique() >= 2:
        dates = sorted(lab["date"].unique())
        split_ok = True
        n = len(dates)
        split_plan = {
            "train_dates": dates[: max(1, int(n * 0.6))],
            "valid_dates": dates[max(1, int(n * 0.6)) : max(1, int(n * 0.8))],
            "test_dates": dates[max(1, int(n * 0.8)) :],
        }
    else:
        split_ok = False
        split_plan = {"reason": "need ≥2 calendar days of labeled rows"}

    if len(by_date):
        dti = pd.to_datetime(sorted(by_date.index))
        gaps = dti.to_series().diff().dt.days.fillna(1)
        max_consecutive = 1
        cur = 1
        for g in gaps.iloc[1:]:
            if g == 1:
                cur += 1
                max_consecutive = max(max_consecutive, cur)
            else:
                cur = 1
    else:
        max_consecutive = 0

    result = {
        "ok": True,
        "primary_horizon_min": PRIMARY,
        "match_tolerance_minutes": TOL_MINUTES,
        "label_definition": {
            "1": "at ~t+h, ≥1 charger actually observed as available (stat=2)",
            "0": "at ~t+h, usable chargers observed and available_observed=0",
            "null": "no reliable observation near t+h (NOT converted to 0)",
        },
        "horizons": horizon_stats,
        "eta15": horizon_stats["15"],
        "by_station_label_count_describe": by_station,
        "temporal_split_feasible": split_ok,
        "temporal_split_plan": split_plan,
        "max_consecutive_label_days": max_consecutive,
        "station_filter": "stations with ≥3 ticks that have observed_chargers>0",
        "bias_note": (
            "Labels require change-feed observation at horizon — quiet stations under-labeled. "
            "Reconstruct-only availability is NOT used as target."
        ),
    }

    try:
        import matplotlib.pyplot as plt

        if len(by_date):
            fig, ax = plt.subplots(figsize=(8, 4))
            ax.bar(range(len(by_date)), by_date.values, color="#2c5f6e")
            ax.set_xticks(range(len(by_date)))
            ax.set_xticklabels(list(by_date.index), rotation=45, ha="right")
            ax.set_ylabel("Labeled rows")
            ax.set_title("ETA 15m labels by date")
            fig.tight_layout()
            fig.savefig(OUT_FIGURES / "eta15_labels_by_date.png", dpi=120)
            plt.close(fig)
        if len(by_hour):
            fig, ax = plt.subplots(figsize=(8, 4))
            ax.bar(by_hour.index, by_hour.values, color="#2c5f6e")
            ax.set_xlabel("Hour")
            ax.set_ylabel("Labeled rows")
            ax.set_title("ETA 15m labels by hour")
            fig.tight_layout()
            fig.savefig(OUT_FIGURES / "eta15_labels_by_hour.png", dpi=120)
            plt.close(fig)
    except Exception as exc:  # noqa: BLE001
        result["figure_error"] = str(exc)

    (OUT_JSON / "eta_targets.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    return result
