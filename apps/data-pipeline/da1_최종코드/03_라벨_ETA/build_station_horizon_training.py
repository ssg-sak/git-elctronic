"""Build the DA① station×time×horizon model-training handoff.

The builder is model-independent. It creates conservative binary labels:

* positive: at least one charger is known available at the arrival tick;
* negative: every charger is known and none is available;
* partial unknown: excluded from the fit-ready dataset.

All model features are available at ``feature_as_of``. Future columns are
retained only as label-audit fields and are never listed as model inputs.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.feature_selection import mutual_info_classif
from sklearn.metrics import roc_auc_score

_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))

from _bootstrap import ensure_paths

_ANALYSIS = Path(__file__).resolve().parent
if str(_ANALYSIS) not in sys.path:
    sys.path.insert(0, str(_ANALYSIS))

from build_arrival_availability_replay import future_tick_map

REPO = ensure_paths()
DEFAULT_PANEL = (
    REPO
    / "apps"
    / "data-pipeline"
    / "reports"
    / "timeseries_feasibility"
    / "tables"
    / "station_tick_panel.parquet"
)
DEFAULT_D1 = (
    REPO
    / "apps"
    / "data-pipeline"
    / "evaluation"
    / "results"
    / "datasets"
    / "station_feature_snapshot_latest.csv"
)
DEFAULT_HISTORY_META = (
    REPO
    / "apps"
    / "data-pipeline"
    / "evaluation"
    / "results"
    / "datasets"
    / "station_history_features_meta.json"
)
DEFAULT_DATASET_DIR = (
    REPO / "apps" / "data-pipeline" / "evaluation" / "results" / "datasets"
)
DEFAULT_HORIZONS = (5, 10, 15, 30)
MAX_HOLD_MINUTES = 25

IDENTIFIER_COLUMNS = [
    "station_id",
    "station_name",
    "feature_as_of",
    "target_time",
    "label_observed_at",
    "label_match_delta_minutes",
    "split",
    "source_snapshot_id",
]
TARGET_COLUMNS = [
    "target_available",
    "label_reason",
    "label_quality",
    "label_source",
]
MODEL_FEATURES = [
    "horizon_minutes",
    "available_count",
    "usable_count",
    "known_charger_count",
    "direct_observed_count",
    "total_chargers",
    "observation_coverage",
    "direct_observation_coverage",
    "observation_age_minutes",
    "available_count_delta_1tick",
    "minutes_since_last_change",
    "hour",
    "weekday",
    "is_weekend",
    "sessions_per_charger",
    "usage_daytype_avg",
    "history_observed",
]
AUXILIARY_FEATURE_COLUMNS = ["unobserved_rate"]
ASSOCIATION_FEATURES = MODEL_FEATURES + AUXILIARY_FEATURE_COLUMNS
LABEL_AUDIT_COLUMNS = [
    "target_known_chargers",
    "target_total_chargers",
    "target_observation_coverage",
]
REQUIRED_PANEL_COLUMNS = {
    "station_id",
    "panel_time",
    "chargers",
    "observed_chargers",
    "known_recon",
    "available_recon",
    "usable_recon",
    "observation_age_minutes",
    "snapshotId",
    "collection_success",
}
REQUIRED_D1_COLUMNS = {
    "statId",
    "statNm",
    "coord_ok",
    "recommend_public_default",
    "sessions_per_charger",
    "usage_weekday_avg",
    "usage_weekend_avg",
    "history_observed",
}
REQUIRED_DOMAIN_FEATURES = {
    "horizon_minutes",
    "available_count",
    "known_charger_count",
    "total_chargers",
    "observation_coverage",
    "observation_age_minutes",
}


@dataclass(frozen=True)
class BuildArtifacts:
    dataset_path: Path
    sample_path: Path
    report_dir: Path


def truth(series: pd.Series) -> pd.Series:
    return series.astype(str).str.lower().isin({"true", "1", "yes", "y"})


def conservative_target(
    future_available: np.ndarray,
    future_known: np.ndarray,
    future_total: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Return conservative target and reason arrays."""
    target = np.full(future_available.shape, np.nan, dtype=float)
    reason = np.full(future_available.shape, "partial_unknown", dtype=object)

    positive = (future_known > 0) & (future_available > 0)
    negative = (
        (future_total > 0)
        & (future_known >= future_total)
        & (future_available == 0)
    )
    target[positive] = 1.0
    target[negative] = 0.0
    reason[positive] = "confirmed_positive"
    reason[negative] = "full_coverage_negative"
    return target, reason


def assign_temporal_split(dates: pd.Series) -> pd.Series:
    """Assign non-overlapping 60/20/20-ish date blocks."""
    normalized = pd.to_datetime(dates).dt.date.astype(str)
    unique_dates = sorted(normalized.dropna().unique())
    if len(unique_dates) < 3:
        raise ValueError("temporal split requires at least three distinct dates")

    n_dates = len(unique_dates)
    train_end = max(1, int(math.floor(n_dates * 0.60)))
    valid_end = max(train_end + 1, int(math.floor(n_dates * 0.80)))
    valid_end = min(valid_end, n_dates - 1)

    train_dates = set(unique_dates[:train_end])
    valid_dates = set(unique_dates[train_end:valid_end])
    test_dates = set(unique_dates[valid_end:])
    if not train_dates or not valid_dates or not test_dates:
        raise ValueError("temporal split produced an empty partition")

    return normalized.map(
        lambda value: (
            "train"
            if value in train_dates
            else "valid"
            if value in valid_dates
            else "test"
        )
    )


def benjamini_hochberg(p_values: Iterable[float | None]) -> np.ndarray:
    """Benjamini-Hochberg false-discovery-rate adjustment."""
    values = np.asarray(
        [np.nan if value is None else float(value) for value in p_values],
        dtype=float,
    )
    result = np.full(values.shape, np.nan, dtype=float)
    valid_index = np.where(np.isfinite(values))[0]
    if not len(valid_index):
        return result

    ordered_index = valid_index[np.argsort(values[valid_index])]
    ordered_p = values[ordered_index]
    n = len(ordered_p)
    adjusted = ordered_p * n / np.arange(1, n + 1)
    adjusted = np.minimum.accumulate(adjusted[::-1])[::-1]
    adjusted = np.clip(adjusted, 0, 1)
    result[ordered_index] = adjusted
    return result


def _read_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)
    return pd.read_csv(path, low_memory=False)


def _require_columns(
    frame: pd.DataFrame,
    required: set[str],
    *,
    dataset_name: str,
) -> None:
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"{dataset_name} missing columns: {sorted(missing)}")


def _matrix(
    panel: pd.DataFrame,
    *,
    value: str,
    times: pd.DatetimeIndex,
    station_ids: list[str],
) -> np.ndarray:
    return (
        panel.pivot(index="panel_time", columns="station_id", values=value)
        .reindex(index=times, columns=station_ids)
        .to_numpy()
    )


def _change_features(
    times: pd.DatetimeIndex,
    available: np.ndarray,
    known: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Calculate past-only one-tick delta and minutes since count change."""
    n_ticks, n_stations = available.shape
    delta = np.full((n_ticks, n_stations), np.nan, dtype=float)
    since_change = np.full((n_ticks, n_stations), np.nan, dtype=float)
    last_value = np.full(n_stations, np.nan, dtype=float)
    last_change_ns = np.full(n_stations, -1, dtype=np.int64)
    time_ns = times.astype("datetime64[ns]").view("int64")

    for index in range(n_ticks):
        if (
            index > 0
            and times[index] - times[index - 1]
            > pd.Timedelta(minutes=MAX_HOLD_MINUTES)
        ):
            last_value[:] = np.nan
            last_change_ns[:] = -1

        valid = known[index] > 0
        previous_valid = valid & np.isfinite(last_value)
        delta[index, previous_valid] = (
            available[index, previous_valid] - last_value[previous_valid]
        )
        new_state = valid & ~np.isfinite(last_value)
        changed = previous_valid & (delta[index] != 0)
        last_change_ns[new_state | changed] = time_ns[index]
        since_change[index, valid] = (
            time_ns[index] - last_change_ns[valid]
        ) / pd.Timedelta(minutes=1).value
        last_value[valid] = available[index, valid]
        last_value[~valid] = np.nan
        last_change_ns[~valid] = -1

    return delta, since_change


def _eligible_metadata(d1: pd.DataFrame, panel: pd.DataFrame) -> pd.DataFrame:
    d1 = d1.copy()
    d1["statId"] = d1["statId"].astype(str)
    eligible = truth(d1["coord_ok"]) & truth(d1["recommend_public_default"])
    fields = [
        "statId",
        "statNm",
        "sessions_per_charger",
        "usage_weekday_avg",
        "usage_weekend_avg",
        "history_observed",
    ]
    meta = (
        d1.loc[eligible, fields]
        .drop_duplicates("statId")
        .rename(
            columns={
                "statId": "station_id",
                "statNm": "station_name",
            }
        )
    )
    present = set(panel["station_id"].astype(str).unique())
    meta = meta[meta["station_id"].isin(present)].copy()
    for column in [
        "sessions_per_charger",
        "usage_weekday_avg",
        "usage_weekend_avg",
    ]:
        meta[column] = pd.to_numeric(meta[column], errors="coerce")
    meta["history_observed"] = truth(meta["history_observed"])
    return meta.sort_values("station_id").reset_index(drop=True)


def _build_training_rows(
    panel: pd.DataFrame,
    d1: pd.DataFrame,
    horizons: tuple[int, ...],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    panel = panel.copy()
    panel["station_id"] = panel["station_id"].astype(str)
    panel["panel_time"] = pd.to_datetime(panel["panel_time"])
    panel = panel.sort_values(["panel_time", "station_id"]).reset_index(drop=True)

    duplicated_grain = int(
        panel.duplicated(["station_id", "panel_time"], keep=False).sum()
    )
    if duplicated_grain:
        raise ValueError(
            f"panel has {duplicated_grain} duplicate station×time rows"
        )

    meta = _eligible_metadata(d1, panel)
    station_ids = meta["station_id"].tolist()
    panel = panel[panel["station_id"].isin(station_ids)].copy()
    times = pd.DatetimeIndex(sorted(panel["panel_time"].unique()))
    if len(times) < 3 or not station_ids:
        raise ValueError("panel has insufficient eligible stations or ticks")

    available = _matrix(
        panel,
        value="available_recon",
        times=times,
        station_ids=station_ids,
    )
    usable = _matrix(
        panel,
        value="usable_recon",
        times=times,
        station_ids=station_ids,
    )
    known = _matrix(
        panel,
        value="known_recon",
        times=times,
        station_ids=station_ids,
    )
    direct_observed = _matrix(
        panel,
        value="observed_chargers",
        times=times,
        station_ids=station_ids,
    )
    total = _matrix(
        panel,
        value="chargers",
        times=times,
        station_ids=station_ids,
    )
    observation_age = _matrix(
        panel,
        value="observation_age_minutes",
        times=times,
        station_ids=station_ids,
    )
    snapshot_matrix = (
        panel.pivot(
            index="panel_time",
            columns="station_id",
            values="snapshotId",
        )
        .reindex(index=times, columns=station_ids)
        .to_numpy(dtype=object)
    )
    success_by_tick = (
        panel.groupby("panel_time")["collection_success"]
        .first()
        .reindex(times)
        .astype(bool)
        .to_numpy()
    )

    delta, since_change = _change_features(times, available, known)
    meta_by_station = meta.set_index("station_id").reindex(station_ids)
    station_name = meta_by_station["station_name"].to_numpy(dtype=object)
    sessions_per_charger = meta_by_station["sessions_per_charger"].to_numpy(
        dtype=float
    )
    weekday_usage = meta_by_station["usage_weekday_avg"].to_numpy(dtype=float)
    weekend_usage = meta_by_station["usage_weekend_avg"].to_numpy(dtype=float)
    history_observed = meta_by_station["history_observed"].to_numpy(dtype=bool)

    frames: list[pd.DataFrame] = []
    horizon_profile: dict[str, Any] = {}
    current_candidate = (known > 0) & success_by_tick[:, None]
    for horizon in horizons:
        mapping = future_tick_map(times, horizon)
        source_tick_index = np.where(mapping >= 0)[0]
        future_tick_index = mapping[source_tick_index]

        future_available = available[future_tick_index]
        future_known = known[future_tick_index]
        future_total = total[future_tick_index]
        target, reason = conservative_target(
            future_available,
            future_known,
            future_total,
        )
        candidate = (
            current_candidate[source_tick_index]
            & success_by_tick[future_tick_index, None]
        )
        labelable = candidate & np.isfinite(target)
        row_index, station_index = np.where(labelable)
        if not len(row_index):
            horizon_profile[str(horizon)] = {
                "candidate_rows": int(candidate.sum()),
                "labeled_rows": 0,
            }
            continue

        source_rows = source_tick_index[row_index]
        future_rows = future_tick_index[row_index]
        current_total = total[source_rows, station_index]
        current_known = known[source_rows, station_index]
        current_direct = direct_observed[source_rows, station_index]
        future_known_selected = future_known[row_index, station_index]
        future_total_selected = future_total[row_index, station_index]
        feature_time = times[source_rows]
        label_time = times[future_rows]
        weekend = feature_time.weekday >= 5

        frame = pd.DataFrame(
            {
                "station_id": np.asarray(station_ids)[station_index],
                "station_name": station_name[station_index],
                "feature_as_of": feature_time,
                "horizon_minutes": int(horizon),
                "target_time": feature_time
                + pd.to_timedelta(horizon, unit="m"),
                "label_observed_at": label_time,
                "label_match_delta_minutes": (
                    (
                        label_time
                        - (
                            feature_time
                            + pd.to_timedelta(horizon, unit="m")
                        )
                    ).total_seconds()
                    / 60
                ),
                "target_available": target[row_index, station_index].astype(
                    np.int8
                ),
                "label_reason": reason[row_index, station_index],
                "label_quality": np.where(
                    target[row_index, station_index] == 1,
                    "CONFIRMED_POSITIVE",
                    "FULL_COVERAGE_NEGATIVE",
                ),
                "label_source": "25m_hold_reconstructed_status",
                "source_snapshot_id": snapshot_matrix[
                    source_rows, station_index
                ],
                "available_count": available[
                    source_rows, station_index
                ].astype(float),
                "usable_count": usable[
                    source_rows, station_index
                ].astype(float),
                "known_charger_count": current_known.astype(float),
                "direct_observed_count": current_direct.astype(float),
                "total_chargers": current_total.astype(float),
                "observation_coverage": np.divide(
                    current_known,
                    current_total,
                    out=np.full_like(current_known, np.nan, dtype=float),
                    where=current_total > 0,
                ),
                "direct_observation_coverage": np.divide(
                    current_direct,
                    current_total,
                    out=np.full_like(current_direct, np.nan, dtype=float),
                    where=current_total > 0,
                ),
                "unobserved_rate": np.divide(
                    current_total - current_known,
                    current_total,
                    out=np.full_like(current_known, np.nan, dtype=float),
                    where=current_total > 0,
                ),
                "observation_age_minutes": observation_age[
                    source_rows, station_index
                ],
                "available_count_delta_1tick": delta[
                    source_rows, station_index
                ],
                "minutes_since_last_change": since_change[
                    source_rows, station_index
                ],
                "hour": feature_time.hour.astype(np.int8),
                "weekday": feature_time.weekday.astype(np.int8),
                "is_weekend": weekend,
                "sessions_per_charger": sessions_per_charger[station_index],
                "usage_daytype_avg": np.where(
                    weekend,
                    weekend_usage[station_index],
                    weekday_usage[station_index],
                ),
                "history_observed": history_observed[station_index],
                "target_known_chargers": future_known_selected.astype(float),
                "target_total_chargers": future_total_selected.astype(float),
                "target_observation_coverage": np.divide(
                    future_known_selected,
                    future_total_selected,
                    out=np.full_like(
                        future_known_selected,
                        np.nan,
                        dtype=float,
                    ),
                    where=future_total_selected > 0,
                ),
            }
        )
        frames.append(frame)

        target_values = frame["target_available"]
        horizon_profile[str(horizon)] = {
            "mapped_source_ticks": int(len(source_tick_index)),
            "candidate_rows": int(candidate.sum()),
            "labeled_rows": int(len(frame)),
            "excluded_partial_unknown_rows": int(
                candidate.sum() - labelable.sum()
            ),
            "positive": int((target_values == 1).sum()),
            "negative": int((target_values == 0).sum()),
            "positive_rate": float(target_values.mean()),
            "stations": int(frame["station_id"].nunique()),
        }

    if not frames:
        raise ValueError("no conservative labeled rows were produced")

    training = pd.concat(frames, ignore_index=True)
    training["feature_date"] = (
        pd.to_datetime(training["feature_as_of"]).dt.date.astype(str)
    )
    training["split"] = assign_temporal_split(training["feature_date"])

    ordered = (
        IDENTIFIER_COLUMNS
        + TARGET_COLUMNS
        + MODEL_FEATURES
        + AUXILIARY_FEATURE_COLUMNS
        + LABEL_AUDIT_COLUMNS
        + ["feature_date"]
    )
    training = training[ordered].sort_values(
        ["feature_as_of", "station_id", "horizon_minutes"]
    )
    return training.reset_index(drop=True), {
        "eligible_stations": int(len(station_ids)),
        "panel_ticks": int(len(times)),
        "panel_first_tick": times.min().isoformat(),
        "panel_latest_tick": times.max().isoformat(),
        "horizons": horizon_profile,
    }


def _safe_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _blocked_auc_interval(
    values: pd.Series,
    target: pd.Series,
    blocks: pd.Series,
    *,
    iterations: int,
    random_state: int = 42,
    max_rows_per_block: int = 1_000,
) -> tuple[float | None, float | None, float | None]:
    data = pd.DataFrame(
        {
            "x": pd.to_numeric(values, errors="coerce"),
            "y": pd.to_numeric(target, errors="coerce"),
            "block": blocks.astype(str),
        }
    ).dropna()
    if data["y"].nunique() < 2 or data["x"].nunique() < 2:
        return None, None, None

    rng = np.random.default_rng(random_state)
    grouped: dict[str, pd.DataFrame] = {}
    for name, group in data.groupby("block", sort=True):
        if len(group) > max_rows_per_block:
            group = group.sample(
                n=max_rows_per_block,
                random_state=random_state,
            )
        grouped[str(name)] = group
    names = list(grouped)
    if len(names) < 2:
        return None, None, None

    balanced = pd.concat(
        [grouped[name] for name in names],
        ignore_index=True,
    )
    balanced_auc_raw = float(
        roc_auc_score(balanced["y"], balanced["x"])
    )
    balanced_auc = max(balanced_auc_raw, 1.0 - balanced_auc_raw)

    estimates: list[float] = []
    for _ in range(iterations):
        sampled_names = rng.choice(names, size=len(names), replace=True)
        sample = pd.concat(
            [grouped[str(name)] for name in sampled_names],
            ignore_index=True,
        )
        if sample["y"].nunique() < 2 or sample["x"].nunique() < 2:
            continue
        auc = roc_auc_score(sample["y"], sample["x"])
        estimates.append(max(float(auc), 1.0 - float(auc)))
    if not estimates:
        return balanced_auc, None, None
    low, high = np.quantile(estimates, [0.025, 0.975])
    return balanced_auc, float(low), float(high)


def _association_row(
    frame: pd.DataFrame,
    feature: str,
    *,
    block_column: str,
    bootstrap_iterations: int,
) -> dict[str, Any]:
    numeric = pd.to_numeric(frame[feature], errors="coerce")
    target = pd.to_numeric(frame["target_available"], errors="coerce")
    valid = numeric.notna() & target.notna()
    x = numeric[valid]
    y = target[valid]
    row: dict[str, Any] = {
        "feature": feature,
        "rows": int(valid.sum()),
        "null_rate": float(1 - valid.mean()),
        "distinct_values": int(x.nunique()),
        "positive_rate": float(y.mean()) if len(y) else None,
        "point_biserial": None,
        "p_value": None,
        "spearman": None,
        "directional_auc": None,
        "blocked_auc": None,
        "auc_ci_low": None,
        "auc_ci_high": None,
        "mutual_information": None,
    }
    if len(x) < 20 or x.nunique() < 2 or y.nunique() < 2:
        return row

    try:
        corr, p_value = stats.pointbiserialr(y, x)
        row["point_biserial"] = _safe_number(corr)
        row["p_value"] = _safe_number(p_value)
    except Exception:  # noqa: BLE001
        pass
    try:
        spearman = stats.spearmanr(x, y).statistic
        row["spearman"] = _safe_number(spearman)
    except Exception:  # noqa: BLE001
        pass
    try:
        auc = float(roc_auc_score(y, x))
        row["directional_auc"] = max(auc, 1.0 - auc)
        blocked_auc, low, high = _blocked_auc_interval(
            x,
            y,
            frame.loc[valid, block_column],
            iterations=bootstrap_iterations,
        )
        row["blocked_auc"] = blocked_auc
        row["auc_ci_low"] = low
        row["auc_ci_high"] = high
    except Exception:  # noqa: BLE001
        pass
    try:
        sample = pd.DataFrame({"x": x, "y": y})
        if len(sample) > 50_000:
            sample = sample.sample(n=50_000, random_state=42)
        mi = mutual_info_classif(
            sample[["x"]].to_numpy(),
            sample["y"].astype(int).to_numpy(),
            discrete_features=False,
            random_state=42,
        )[0]
        row["mutual_information"] = _safe_number(mi)
    except Exception:  # noqa: BLE001
        pass
    return row


def build_associations(
    training: pd.DataFrame,
    *,
    bootstrap_iterations: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    train = training[training["split"] == "train"].copy()
    overall_rows = [
        _association_row(
            train,
            feature,
            block_column="feature_date",
            bootstrap_iterations=bootstrap_iterations,
        )
        for feature in ASSOCIATION_FEATURES
    ]
    overall = pd.DataFrame(overall_rows)
    overall["q_value"] = benjamini_hochberg(overall["p_value"])

    horizon_rows: list[dict[str, Any]] = []
    for horizon, group in train.groupby("horizon_minutes", sort=True):
        rows = [
            {
                "horizon_minutes": int(horizon),
                **_association_row(
                    group,
                    feature,
                    block_column="feature_date",
                    bootstrap_iterations=bootstrap_iterations,
                ),
            }
            for feature in ASSOCIATION_FEATURES
        ]
        horizon_frame = pd.DataFrame(rows)
        horizon_frame["q_value"] = benjamini_hochberg(
            horizon_frame["p_value"]
        )
        horizon_rows.extend(horizon_frame.to_dict("records"))
    by_horizon = pd.DataFrame(horizon_rows)
    return overall, by_horizon


def _feature_decisions(
    overall: pd.DataFrame,
    by_horizon: pd.DataFrame,
) -> dict[str, Any]:
    decisions: list[dict[str, Any]] = []
    for row in overall.to_dict("records"):
        feature = str(row["feature"])
        null_rate = _safe_number(row.get("null_rate")) or 0.0
        distinct = int(row.get("distinct_values") or 0)
        q_value = _safe_number(row.get("q_value"))
        auc_low = _safe_number(row.get("auc_ci_low"))
        directional_auc = _safe_number(row.get("directional_auc"))
        blocked_auc = _safe_number(row.get("blocked_auc"))
        practical_auc = (
            min(directional_auc, blocked_auc)
            if directional_auc is not None and blocked_auc is not None
            else directional_auc or blocked_auc
        )

        horizon = by_horizon[by_horizon["feature"] == feature]
        signs = [
            int(np.sign(value))
            for value in pd.to_numeric(
                horizon["point_biserial"],
                errors="coerce",
            ).dropna()
            if value != 0
        ]
        direction_stable = len(set(signs)) <= 1

        if feature == "unobserved_rate":
            decision = "EXCLUDE_REDUNDANT"
            reason = "exact complement of observation_coverage"
        elif feature in {
            "sessions_per_charger",
            "usage_daytype_avg",
            "history_observed",
        }:
            decision = "HOLD_SPARSE_HISTORY"
            reason = "usage-history coverage is too sparse for a default feature"
        elif distinct < 2:
            decision = "EXCLUDE"
            reason = "constant or single-valued in train"
        elif null_rate > 0.90:
            decision = "HOLD"
            reason = "train null rate exceeds 90%"
        elif feature in REQUIRED_DOMAIN_FEATURES:
            decision = "RETAIN_FOR_ABLATION"
            reason = "required domain feature; DA② ablation still required"
        elif (
            q_value is not None
            and q_value < 0.05
            and auc_low is not None
            and auc_low > 0.5
            and practical_auc is not None
            and practical_auc >= 0.55
            and direction_stable
        ):
            decision = "RETAIN_CANDIDATE"
            reason = "adjusted significance, blocked AUC, and horizon direction pass"
        elif (
            practical_auc is not None
            and practical_auc >= 0.55
            and direction_stable
        ):
            decision = "RETAIN_CANDIDATE"
            reason = "practical univariate discrimination and stable direction"
        else:
            decision = "HOLD_FOR_HGB_INTERACTION_TEST"
            reason = "weak univariate evidence; nonlinear interaction may remain"

        decisions.append(
            {
                "feature": feature,
                "decision": decision,
                "reason": reason,
                "null_rate": null_rate,
                "directional_auc": directional_auc,
                "blocked_auc": blocked_auc,
                "practical_auc": practical_auc,
                "auc_ci_low": auc_low,
                "q_value": q_value,
                "horizon_direction_stable": direction_stable,
                "owner_next": (
                    "DA②"
                    if decision
                    in {
                        "RETAIN_FOR_ABLATION",
                        "RETAIN_CANDIDATE",
                        "HOLD_FOR_HGB_INTERACTION_TEST",
                    }
                    else "DA①"
                ),
            }
        )
    return {
        "status": "DA1_UNIVARIATE_COMPLETE_DA2_ABLATION_PENDING",
        "rules": {
            "correlation_hard_gate": False,
            "adjusted_significance": "q_value < 0.05",
            "blocked_auc": "95% CI lower bound > 0.5",
            "practical_auc_candidate": "directional_auc >= 0.55",
            "required_features": sorted(REQUIRED_DOMAIN_FEATURES),
        },
        "decisions": decisions,
    }


def _column_schema() -> dict[str, Any]:
    descriptions: dict[str, tuple[str, str, bool, str | None, str]] = {
        "station_id": ("identifier", "string", False, None, "charging station ID"),
        "station_name": ("metadata", "string", True, None, "charging station name"),
        "feature_as_of": ("identifier", "datetime64[ns]", False, "KST", "feature cutoff time"),
        "target_time": ("audit", "datetime64[ns]", False, "KST", "feature_as_of plus horizon"),
        "label_observed_at": ("audit", "datetime64[ns]", False, "KST", "future tick used for label"),
        "label_match_delta_minutes": ("audit", "float64", False, "minutes", "matched tick minus target time"),
        "split": ("identifier", "string", False, None, "date-block train/valid/test"),
        "source_snapshot_id": ("audit", "string", False, None, "source tick snapshot ID"),
        "target_available": ("target", "int8", False, "0/1", "arrival availability label"),
        "label_reason": ("audit", "string", False, None, "conservative label reason"),
        "label_quality": ("audit", "string", False, None, "positive or full-coverage negative"),
        "label_source": ("audit", "string", False, None, "label reconstruction method"),
        "horizon_minutes": ("feature", "int64", False, "minutes", "arrival horizon"),
        "available_count": ("feature", "float64", False, "chargers", "known available chargers at cutoff"),
        "usable_count": ("feature", "float64", False, "chargers", "known status 2 or 3 chargers"),
        "known_charger_count": ("feature", "float64", False, "chargers", "chargers known after bounded hold"),
        "direct_observed_count": ("feature", "float64", False, "chargers", "chargers directly observed at tick"),
        "total_chargers": ("feature", "float64", False, "chargers", "station charger count"),
        "observation_coverage": ("feature", "float64", False, "0~1", "known over total chargers"),
        "direct_observation_coverage": ("feature", "float64", False, "0~1", "direct observed over total"),
        "unobserved_rate": ("audit", "float64", False, "0~1", "redundant complement of observation coverage"),
        "observation_age_minutes": ("feature", "float64", True, "minutes", "freshest known charger observation age"),
        "available_count_delta_1tick": ("feature", "float64", True, "chargers", "past-only change from prior continuous tick"),
        "minutes_since_last_change": ("feature", "float64", True, "minutes", "past-only elapsed time since count change"),
        "hour": ("feature", "int8", False, "0~23", "feature cutoff hour"),
        "weekday": ("feature", "int8", False, "0~6", "Monday zero weekday"),
        "is_weekend": ("feature", "bool", False, None, "Saturday or Sunday"),
        "sessions_per_charger": ("feature", "float64", True, "sessions", "historical sessions per charger"),
        "usage_daytype_avg": ("feature", "float64", True, "sessions/day", "historical weekday or weekend mean"),
        "history_observed": ("feature", "bool", False, None, "usage-history join indicator"),
        "target_known_chargers": ("audit", "float64", False, "chargers", "known chargers at label tick"),
        "target_total_chargers": ("audit", "float64", False, "chargers", "total chargers at label tick"),
        "target_observation_coverage": ("audit", "float64", False, "0~1", "label-tick known coverage"),
        "feature_date": ("identifier", "string", False, "YYYY-MM-DD", "split date"),
    }
    columns = []
    for name in (
        IDENTIFIER_COLUMNS
        + TARGET_COLUMNS
        + MODEL_FEATURES
        + AUXILIARY_FEATURE_COLUMNS
        + LABEL_AUDIT_COLUMNS
        + ["feature_date"]
    ):
        role, dtype, nullable, unit, description = descriptions[name]
        columns.append(
            {
                "name": name,
                "role": role,
                "model_input": name in MODEL_FEATURES,
                "dtype": dtype,
                "nullable": nullable,
                "unit": unit,
                "description": description,
            }
        )
    return {
        "version": "hgb_feature_schema_v1",
        "status": "DA1_READY_PENDING_DA2_ACCEPTANCE",
        "dataset": "station_horizon_training_v1",
        "grain": "station_id × feature_as_of × horizon_minutes",
        "primary_key": [
            "station_id",
            "feature_as_of",
            "horizon_minutes",
        ],
        "target": "target_available",
        "model_features": MODEL_FEATURES,
        "auxiliary_pre_cutoff_columns": AUXILIARY_FEATURE_COLUMNS,
        "columns": columns,
        "excluded_from_model": {
            "future_audit_columns": LABEL_AUDIT_COLUMNS
            + ["target_time", "label_observed_at"],
            "reason": "post-cutoff information is label audit only",
        },
    }


def _history_meta(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"available": False}
    return {
        "available": True,
        **json.loads(path.read_text(encoding="utf-8")),
    }


def _quality_report(
    training: pd.DataFrame,
    *,
    source_profile: dict[str, Any],
    history_meta: dict[str, Any],
) -> dict[str, Any]:
    key = ["station_id", "feature_as_of", "horizon_minutes"]
    duplicate_rows = int(training.duplicated(key, keep=False).sum())
    target_invalid = int(
        (~training["target_available"].isin([0, 1])).sum()
    )
    time_travel = int(
        (
            pd.to_datetime(training["feature_as_of"])
            >= pd.to_datetime(training["label_observed_at"])
        ).sum()
    )
    split_dates = {
        split: sorted(group["feature_date"].unique().tolist())
        for split, group in training.groupby("split")
    }
    split_overlap = any(
        set(split_dates.get(left, [])) & set(split_dates.get(right, []))
        for left, right in [
            ("train", "valid"),
            ("train", "test"),
            ("valid", "test"),
        ]
    )
    chronology_ok = (
        max(split_dates["train"]) < min(split_dates["valid"])
        and max(split_dates["valid"]) < min(split_dates["test"])
    )
    history_before_features = True
    if history_meta.get("date_max"):
        history_before_features = (
            pd.Timestamp(history_meta["date_max"])
            < pd.to_datetime(training["feature_as_of"]).min()
        )

    positive_rate = float(training["target_available"].mean())
    panel_days = int(training["feature_date"].nunique())
    history_coverage = float(training["history_observed"].mean())
    horizon_pair = (
        training[training["horizon_minutes"].isin([5, 10])]
        .pivot_table(
            index=["station_id", "feature_as_of"],
            columns="horizon_minutes",
            values="target_available",
            aggfunc="first",
        )
        .dropna()
    )
    same_5m_10m_rate = (
        float((horizon_pair[5] == horizon_pair[10]).mean())
        if {5, 10}.issubset(horizon_pair.columns) and len(horizon_pair)
        else None
    )

    checks = [
        {
            "code": "PRIMARY_KEY_UNIQUENESS",
            "status": "PASS" if duplicate_rows == 0 else "FAIL",
            "evidence": {"duplicate_rows": duplicate_rows, "key": key},
        },
        {
            "code": "TARGET_VALIDITY",
            "status": "PASS" if target_invalid == 0 else "FAIL",
            "evidence": {
                "invalid_rows": target_invalid,
                "allowed": [0, 1],
                "null_rows": int(training["target_available"].isna().sum()),
            },
        },
        {
            "code": "NO_TIME_TRAVEL",
            "status": "PASS" if time_travel == 0 else "FAIL",
            "evidence": {"feature_at_or_after_label_rows": time_travel},
        },
        {
            "code": "TEMPORAL_SPLIT",
            "status": (
                "PASS" if not split_overlap and chronology_ok else "FAIL"
            ),
            "evidence": {
                "dates": split_dates,
                "overlap": split_overlap,
                "chronology_ok": chronology_ok,
            },
        },
        {
            "code": "HISTORY_PRECEDES_PANEL",
            "status": "PASS" if history_before_features else "FAIL",
            "evidence": {
                "history_date_max": history_meta.get("date_max"),
                "panel_feature_min": str(training["feature_as_of"].min()),
            },
        },
        {
            "code": "CONSERVATIVE_NEGATIVE_LABEL",
            "status": "PASS",
            "evidence": {
                "negative_rows": int(
                    (training["target_available"] == 0).sum()
                ),
                "negative_min_target_coverage": _safe_number(
                    training.loc[
                        training["target_available"] == 0,
                        "target_observation_coverage",
                    ].min()
                ),
                "rule": "negative only when all station chargers are known",
            },
        },
        {
            "code": "CLASS_IMBALANCE",
            "status": "WARN" if positive_rate > 0.90 else "PASS",
            "evidence": {
                "positive_rate": positive_rate,
                "negative_rows": int(
                    (training["target_available"] == 0).sum()
                ),
                "note": "DA② should use class-aware metrics and weighting tests",
            },
        },
        {
            "code": "HORIZON_DISTINCTNESS_5M_10M",
            "status": (
                "WARN"
                if same_5m_10m_rate is not None
                and same_5m_10m_rate > 0.95
                else "PASS"
            ),
            "evidence": {
                "paired_rows": int(len(horizon_pair)),
                "same_target_rate": same_5m_10m_rate,
                "collection_cadence_note": (
                    "approximately 10-minute ticks can map 5m and 10m "
                    "to the same future observation"
                ),
            },
        },
        {
            "code": "TIME_COVERAGE",
            "status": "WARN" if panel_days < 14 else "PASS",
            "evidence": {
                "distinct_dates": panel_days,
                "recommended_minimum_for_model_acceptance": 14,
            },
        },
        {
            "code": "USAGE_HISTORY_COVERAGE",
            "status": "WARN" if history_coverage < 0.20 else "PASS",
            "evidence": {
                "history_observed_rate": history_coverage,
                "policy": "sparse history features are optional, not default",
            },
        },
    ]
    for split, group in training.groupby("split"):
        for horizon, subgroup in group.groupby("horizon_minutes"):
            negative = int((subgroup["target_available"] == 0).sum())
            checks.append(
                {
                    "code": f"CLASS_SUPPORT_{split.upper()}_{int(horizon)}M",
                    "status": "PASS" if negative >= 100 else "WARN",
                    "evidence": {
                        "rows": int(len(subgroup)),
                        "positive": int(
                            (subgroup["target_available"] == 1).sum()
                        ),
                        "negative": negative,
                    },
                }
            )

    summary = {
        status: sum(check["status"] == status for check in checks)
        for status in ["PASS", "WARN", "FAIL"]
    }
    return {
        "dataset": "station_horizon_training_v1",
        "grain": "station_id × feature_as_of × horizon_minutes",
        "source_profile": source_profile,
        "checks": checks,
        "summary": summary,
        "training_data_handoff_ready": summary["FAIL"] == 0,
        "interpretation": (
            "DA① data handoff readiness only; this does not approve an HGB model."
        ),
    }


def _profile(
    training: pd.DataFrame,
    *,
    source_profile: dict[str, Any],
    history_meta: dict[str, Any],
) -> dict[str, Any]:
    return {
        "dataset": "station_horizon_training_v1",
        "rows": int(len(training)),
        "columns": int(len(training.columns)),
        "stations": int(training["station_id"].nunique()),
        "feature_time_min": pd.Timestamp(
            training["feature_as_of"].min()
        ).isoformat(),
        "feature_time_max": pd.Timestamp(
            training["feature_as_of"].max()
        ).isoformat(),
        "source_profile": source_profile,
        "history_source": {
            "file": history_meta.get("usage_file"),
            "date_min": history_meta.get("date_min"),
            "date_max": history_meta.get("date_max"),
        },
        "rows_by_horizon": {
            str(int(key)): int(value)
            for key, value in training["horizon_minutes"]
            .value_counts()
            .sort_index()
            .items()
        },
        "rows_by_split": {
            str(key): int(value)
            for key, value in training["split"].value_counts().items()
        },
        "target_by_split_horizon": (
            training.groupby(["split", "horizon_minutes"])[
                "target_available"
            ]
            .agg(rows="size", positives="sum", positive_rate="mean")
            .reset_index()
            .to_dict("records")
        ),
        "feature_null_rates": {
            feature: float(training[feature].isna().mean())
            for feature in MODEL_FEATURES
        },
        "model_features": MODEL_FEATURES,
        "caveats": [
            "Positive labels require one known available charger.",
            "Negative labels require full station charger coverage.",
            "Labels use a 25-minute bounded state reconstruction.",
            "Historical usage ends before the panel and is a sparse optional prior.",
            "DA② must run time-out-of-sample ablation and calibration.",
        ],
    }


def _write_outputs(
    training: pd.DataFrame,
    *,
    source_profile: dict[str, Any],
    history_meta: dict[str, Any],
    dataset_dir: Path,
    report_dir: Path,
    sample_rows: int,
    bootstrap_iterations: int,
) -> tuple[BuildArtifacts, dict[str, Any]]:
    dataset_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    dataset_path = dataset_dir / "station_horizon_training_v1.parquet"
    sample_path = dataset_dir / "station_horizon_training_sample.csv"
    training.to_parquet(dataset_path, index=False)
    (
        training.sample(
            n=min(sample_rows, len(training)),
            random_state=42,
        )
        .sort_values(["feature_as_of", "station_id", "horizon_minutes"])
        .to_csv(sample_path, index=False, encoding="utf-8-sig")
    )

    schema = _column_schema()
    (report_dir / "feature_schema_v1.json").write_text(
        json.dumps(schema, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    profile = _profile(
        training,
        source_profile=source_profile,
        history_meta=history_meta,
    )
    (report_dir / "training_dataset_profile.json").write_text(
        json.dumps(profile, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    quality = _quality_report(
        training,
        source_profile=source_profile,
        history_meta=history_meta,
    )
    (report_dir / "training_dataset_quality.json").write_text(
        json.dumps(quality, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    overall, by_horizon = build_associations(
        training,
        bootstrap_iterations=bootstrap_iterations,
    )
    overall.to_csv(
        report_dir / "feature_target_association.csv",
        index=False,
        encoding="utf-8-sig",
    )
    by_horizon.to_csv(
        report_dir / "feature_target_by_horizon.csv",
        index=False,
        encoding="utf-8-sig",
    )
    decisions = _feature_decisions(overall, by_horizon)
    (report_dir / "feature_selection_decisions.json").write_text(
        json.dumps(decisions, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    pd.DataFrame(
        [
            {
                "feature": feature,
                "status": "PENDING_DA2_HGB_ABLATION",
                "owner": "DA②",
                "reason": (
                    "Requires a fitted HGB and time-out-of-sample comparison"
                ),
            }
            for feature in MODEL_FEATURES
        ]
    ).to_csv(
        report_dir / "feature_ablation_metrics.csv",
        index=False,
        encoding="utf-8-sig",
    )

    summary = {
        "status": (
            "DA1_READY_PENDING_DA2_ACCEPTANCE"
            if quality["training_data_handoff_ready"]
            else "DA1_NOT_READY"
        ),
        "dataset": str(dataset_path.relative_to(REPO)).replace("\\", "/"),
        "sample": str(sample_path.relative_to(REPO)).replace("\\", "/"),
        "report_dir": str(report_dir.relative_to(REPO)).replace("\\", "/"),
        "rows": int(len(training)),
        "stations": int(training["station_id"].nunique()),
        "quality_summary": quality["summary"],
        "model_features": len(MODEL_FEATURES),
        "da2_pending": [
            "HGB baseline comparison",
            "time-out-of-sample feature ablation",
            "probability calibration",
            "model acceptance and serving",
        ],
    }
    (report_dir / "HANDOFF_SUMMARY.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return (
        BuildArtifacts(
            dataset_path=dataset_path,
            sample_path=sample_path,
            report_dir=report_dir,
        ),
        summary,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--panel", type=Path, default=DEFAULT_PANEL)
    parser.add_argument("--d1", type=Path, default=DEFAULT_D1)
    parser.add_argument(
        "--history-meta",
        type=Path,
        default=DEFAULT_HISTORY_META,
    )
    parser.add_argument(
        "--horizons",
        type=int,
        nargs="+",
        default=list(DEFAULT_HORIZONS),
    )
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=DEFAULT_DATASET_DIR,
    )
    parser.add_argument("--report-dir", type=Path)
    parser.add_argument("--sample-rows", type=int, default=50_000)
    parser.add_argument("--bootstrap-iterations", type=int, default=100)
    args = parser.parse_args()

    panel = _read_table(args.panel)
    d1 = pd.read_csv(args.d1, low_memory=False)
    _require_columns(panel, REQUIRED_PANEL_COLUMNS, dataset_name="station panel")
    _require_columns(d1, REQUIRED_D1_COLUMNS, dataset_name="D1")

    training, source_profile = _build_training_rows(
        panel,
        d1,
        tuple(sorted(set(args.horizons))),
    )
    latest_date = pd.Timestamp(
        training["feature_as_of"].max()
    ).strftime("%Y%m%d")
    report_dir = args.report_dir or (
        REPO
        / "docs"
        / "data"
        / "analysis"
        / f"hgb_training_pipeline_{latest_date}"
    )
    history_meta = _history_meta(args.history_meta)
    _, summary = _write_outputs(
        training,
        source_profile=source_profile,
        history_meta=history_meta,
        dataset_dir=args.dataset_dir,
        report_dir=report_dir,
        sample_rows=args.sample_rows,
        bootstrap_iterations=args.bootstrap_iterations,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["status"].startswith("DA1_READY") else 1


if __name__ == "__main__":
    raise SystemExit(main())
