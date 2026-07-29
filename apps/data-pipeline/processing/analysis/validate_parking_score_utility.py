"""Gate Team5 parking data before it can affect recommendation scores.

This is an offline analysis: it reads local charger-status snapshots and Team5
exports only.  It deliberately separates:

* nearby parking (a 1 km spatial join; never score evidence), from
* STRONG co-location candidates, and
* a future-availability backtest, which is only allowed when its sample and
  time-coverage gates pass.

Usage (repo root):
    python apps/data-pipeline/processing/analysis/validate_parking_score_utility.py
"""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
try:
    import matplotlib.pyplot as plt
except ImportError:  # Optional: report tables and verdict remain reproducible.
    plt = None

_PROCESSING = Path(__file__).resolve().parents[1]
_DATA_PIPELINE = _PROCESSING.parent
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))
if str(_DATA_PIPELINE) not in sys.path:
    sys.path.insert(0, str(_DATA_PIPELINE))

from _bootstrap import ensure_paths
from features.gap_safe_panel import aggregate_station_features, build_gap_safe_panel
from loop_paths import EXTRACTED_PARKING

REPO = ensure_paths()
KST = ZoneInfo("Asia/Seoul")
COLLOCATION = REPO / "docs/data/analysis/parking_ev_colocation_20260725/charger_parking_pairs_within_100m.csv"
STATION_TICK_PANEL = (
    REPO
    / "apps/data-pipeline/reports/timeseries_feasibility/tables/station_tick_panel.csv"
)
MASTER_TRAINING_PANEL = REPO / "docs/data/quality/master_training_dataset.csv"

# These gates deliberately match the project's feasibility posture: sparse
# observations can support descriptive UX, but not a score-weight claim.
MAX_PARKING_STATUS_LAG_MIN = 10
MIN_COHORT_STATIONS = 10
MIN_COHORT_DAYS = 14
MIN_LABELED_ROWS = 500
MIN_TEST_ROWS = 50
MIN_TEST_DAYS = 2
MIN_BOOTSTRAP_STATIONS = 10
RANDOM_SEED = 42

if plt is not None:
    plt.rcParams["font.family"] = ["Malgun Gothic", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False


def _truth(value: pd.Series) -> pd.Series:
    return value.astype(str).str.lower().isin({"true", "1", "y", "yes"})


def _style(ax) -> None:
    ax.set_facecolor("#ffffff")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.25)


def _kst_naive(value: pd.Series) -> pd.Series:
    """Normalize source timestamps to comparable KST wall-clock timestamps."""
    ts = pd.to_datetime(value, errors="coerce")
    if getattr(ts.dt, "tz", None) is not None:
        return ts.dt.tz_convert(KST).dt.tz_localize(None)
    return ts


def _markdown_table(frame: pd.DataFrame) -> str:
    """Render a small Markdown table without depending on tabulate."""
    if frame.empty:
        return ""
    columns = [str(column) for column in frame.columns]
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in frame.fillna("").astype(str).itertuples(index=False, name=None):
        lines.append("| " + " | ".join(value.replace("|", "\\|") for value in row) + " |")
    return "\n".join(lines)


def _load_status_events() -> pd.DataFrame:
    """Load raw loop events through the canonical loader, without mutation."""
    sandbox = (
        REPO
        / "apps/data-pipeline/evaluation/personal/experiments"
        / "SANDBOX_20260717_status_periodic_collection/src"
    )
    if str(sandbox) not in sys.path:
        sys.path.insert(0, str(sandbox))
    from load_snapshots import load_all_snapshots  # type: ignore[import-not-found]  # noqa: PLC0415

    events = load_all_snapshots()
    if events.empty:
        return events
    required = {"statId", "chgerId", "stat", "snapshotId"}
    missing = required.difference(events.columns)
    if missing:
        raise ValueError(f"status snapshot columns missing: {sorted(missing)}")
    return events


def _parking_history_files() -> list[Path]:
    full = sorted(EXTRACTED_PARKING.glob("team5_full_snapshot_*/parking_realtime_status.csv"))
    incremental = sorted(
        EXTRACTED_PARKING.glob(
            "incremental/*/team5_parking_incremental_*/parking_realtime_status_new.csv"
        )
    )
    return [*full[-1:], *incremental]


def _load_parking_history() -> tuple[pd.DataFrame, list[str]]:
    files = _parking_history_files()
    if not files:
        return pd.DataFrame(), []
    frames = [pd.read_csv(path, low_memory=False) for path in files if path.stat().st_size > 3]
    if not frames:
        return pd.DataFrame(), [str(path.relative_to(REPO)) for path in files]
    parking = pd.concat(frames, ignore_index=True)
    required = {"pklt_id", "collected_at", "remaining_spaces", "occupancy_rate"}
    missing = required.difference(parking.columns)
    if missing:
        raise ValueError(f"Team5 parking columns missing: {sorted(missing)}")
    parking["pklt_id"] = parking["pklt_id"].astype(str)
    parking["collected_at"] = _kst_naive(parking["collected_at"])
    for column in ("remaining_spaces", "occupancy_rate", "total_spaces"):
        if column in parking:
            parking[column] = pd.to_numeric(parking[column], errors="coerce")
    parking = parking.dropna(subset=["pklt_id", "collected_at"]).copy()
    if "id" in parking:
        parking = parking.drop_duplicates("id", keep="last")
    return parking.sort_values(["pklt_id", "collected_at"]), [
        str(path.relative_to(REPO)).replace("\\", "/") for path in files
    ]


def _strong_pairs() -> pd.DataFrame:
    pairs = pd.read_csv(COLLOCATION, dtype=str)
    required = {"matched_id", "statId", "evidence_grade", "distance_m"}
    missing = required.difference(pairs.columns)
    if missing:
        raise ValueError(f"co-location columns missing: {sorted(missing)}")
    pairs["distance_m"] = pd.to_numeric(pairs["distance_m"], errors="coerce")
    strong = pairs[pairs["evidence_grade"].eq("STRONG")].copy()
    strong = strong.rename(columns={"matched_id": "pklt_id", "statId": "station_id"})
    strong["pklt_id"] = strong["pklt_id"].astype(str)
    strong["station_id"] = strong["station_id"].astype(str)
    # A station may be near more than one lot.  Retain only the strongest
    # geometric candidate, avoiding duplicated outcome rows.
    return strong.sort_values("distance_m").drop_duplicates("station_id", keep="first")


def _station_panel() -> pd.DataFrame:
    """Use the already rebuilt, gap-safe station panel when available.

    The master training panel is preferred because it includes the newest
    post-7/22 status period. Reconstructing from raw events takes several
    minutes and would duplicate the feasibility pipeline.
    """
    if MASTER_TRAINING_PANEL.is_file():
        stations = pd.read_csv(MASTER_TRAINING_PANEL, low_memory=False, dtype={"statId": str})
        required = {"statId", "panel_ts", "available_count", "total_chargers"}
        missing = required.difference(stations.columns)
        if missing:
            raise ValueError(f"master training panel columns missing: {sorted(missing)}")
        stations = stations.rename(
            columns={
                "statId": "station_id",
                "panel_ts": "status_at",
                "available_count": "available_at_t",
                "total_chargers": "total_chargers_at_t",
            }
        )
        stations["status_at"] = _kst_naive(stations["status_at"])
        stations["available_at_t"] = pd.to_numeric(stations["available_at_t"], errors="coerce")
        stations["total_chargers_at_t"] = pd.to_numeric(
            stations["total_chargers_at_t"], errors="coerce"
        )
        return stations.dropna(
            subset=["station_id", "status_at", "available_at_t", "total_chargers_at_t"]
        ).sort_values(["station_id", "status_at"])

    if STATION_TICK_PANEL.is_file():
        stations = pd.read_csv(STATION_TICK_PANEL, low_memory=False, dtype={"station_id": str})
        required = {
            "station_id",
            "panel_time",
            "available_recon",
            "chargers",
            "observed_chargers",
        }
        missing = required.difference(stations.columns)
        if missing:
            raise ValueError(f"station tick panel columns missing: {sorted(missing)}")
        stations = stations.rename(
            columns={
                "panel_time": "status_at",
                "available_recon": "available_at_t",
                "chargers": "total_chargers_at_t",
            }
        )
        stations["status_at"] = _kst_naive(stations["status_at"])
        stations["available_at_t"] = pd.to_numeric(stations["available_at_t"], errors="coerce")
        stations["total_chargers_at_t"] = pd.to_numeric(
            stations["total_chargers_at_t"], errors="coerce"
        )
        # A zero can be an observed unavailable state; a zero from a failed
        # collection must not become a negative arrival label.
        stations = stations[
            _truth(stations["collection_success"])
            & pd.to_numeric(stations["observed_chargers"], errors="coerce").gt(0)
        ].copy()
        return stations.dropna(
            subset=["station_id", "status_at", "available_at_t", "total_chargers_at_t"]
        ).sort_values(["station_id", "status_at"])

    events = _load_status_events()
    if events.empty:
        return pd.DataFrame()
    panel = build_gap_safe_panel(events, max_gap_minutes=25)
    stations = aggregate_station_features(panel).rename(
        columns={
            "stationId": "station_id",
            "panel_ts": "status_at",
            "available_count": "available_at_t",
            "total_chargers": "total_chargers_at_t",
        }
    )
    if stations.empty:
        return stations
    stations["station_id"] = stations["station_id"].astype(str)
    stations["status_at"] = _kst_naive(stations["status_at"])
    return stations.dropna(subset=["status_at"]).sort_values(["station_id", "status_at"])


def _join_asof_by_key(
    left: pd.DataFrame,
    right: pd.DataFrame,
    *,
    key: str,
    left_time: str,
    right_time: str,
    tolerance: pd.Timedelta,
) -> pd.DataFrame:
    """merge_asof by key requires globally time-sorted frames."""
    return pd.merge_asof(
        left.sort_values([left_time, key]),
        right.sort_values([right_time, key]),
        left_on=left_time,
        right_on=right_time,
        by=key,
        direction="backward",
        tolerance=tolerance,
    )


def _build_cohort(
    stations: pd.DataFrame, parking: pd.DataFrame, pairs: pd.DataFrame
) -> pd.DataFrame:
    if stations.empty or parking.empty or pairs.empty:
        return pd.DataFrame()
    cohort = stations.merge(
        pairs[["station_id", "pklt_id", "distance_m", "charger_name", "parking_name"]],
        on="station_id",
        how="inner",
    )
    park = parking[
        ["pklt_id", "collected_at", "remaining_spaces", "occupancy_rate", "total_spaces"]
        if "total_spaces" in parking
        else ["pklt_id", "collected_at", "remaining_spaces", "occupancy_rate"]
    ].copy()
    joined = _join_asof_by_key(
        cohort,
        park,
        key="pklt_id",
        left_time="status_at",
        right_time="collected_at",
        tolerance=pd.Timedelta(minutes=MAX_PARKING_STATUS_LAG_MIN),
    )
    joined["parking_lag_minutes"] = (
        joined["status_at"] - joined["collected_at"]
    ).dt.total_seconds() / 60
    joined["parking_realtime_at_t"] = joined["collected_at"].notna()
    joined["available_binary_at_t"] = (joined["available_at_t"] >= 1).astype(int)
    joined["date"] = joined["status_at"].dt.date.astype(str)
    joined["hour"] = joined["status_at"].dt.hour
    joined["weekday"] = joined["status_at"].dt.weekday
    return joined


def _future_labels(cohort: pd.DataFrame, horizon_min: int) -> pd.DataFrame:
    """Attach the first observed station state at/after t+horizon; no leakage."""
    if cohort.empty:
        return cohort
    targets = cohort[
        ["station_id", "status_at", "available_at_t", "total_chargers_at_t"]
    ].rename(
        columns={
            "status_at": "target_at",
            "available_at_t": "future_available_count",
            "total_chargers_at_t": "future_total_chargers",
        }
    )
    targets = targets.drop_duplicates(["station_id", "target_at"]).sort_values(
        ["target_at", "station_id"]
    )
    base = cohort.copy()
    base["target_lookup_at"] = base["status_at"] + pd.Timedelta(minutes=horizon_min)
    labeled = pd.merge_asof(
        base.sort_values(["target_lookup_at", "station_id"]),
        targets,
        left_on="target_lookup_at",
        right_on="target_at",
        by="station_id",
        direction="forward",
        tolerance=pd.Timedelta(minutes=MAX_PARKING_STATUS_LAG_MIN),
    )
    labeled["target_available"] = np.where(
        labeled["future_available_count"].notna(),
        (labeled["future_available_count"] >= 1).astype(float),
        np.nan,
    )
    labeled["horizon_minutes"] = horizon_min
    return labeled


def _auc(y: np.ndarray, p: np.ndarray) -> float | None:
    if len(y) == 0 or len(np.unique(y)) < 2:
        return None
    ranks = pd.Series(p).rank(method="average").to_numpy()
    pos = y == 1
    n_pos, n_neg = int(pos.sum()), int((~pos).sum())
    return float((ranks[pos].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


def _pr_auc(y: np.ndarray, p: np.ndarray) -> float | None:
    if len(y) == 0 or not y.any():
        return None
    order = np.argsort(-p, kind="stable")
    y_sorted = y[order]
    tp = np.cumsum(y_sorted)
    precision = tp / np.arange(1, len(y_sorted) + 1)
    return float(precision[y_sorted == 1].sum() / y.sum())


def _metric_row(name: str, y: np.ndarray, p: np.ndarray) -> dict[str, float | str | None]:
    return {
        "model": name,
        "n_test": int(len(y)),
        "auroc": _auc(y, p),
        "pr_auc": _pr_auc(y, p),
        "brier": float(np.mean((y - p) ** 2)) if len(y) else None,
    }


def _fit_and_compare(labeled: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, object]]:
    usable = labeled[labeled["target_available"].notna() & labeled["parking_realtime_at_t"]].copy()
    if usable.empty:
        return pd.DataFrame(), {"skipped": True, "reason": "no synchronized future labels"}
    # A row whose feature time is on one date but target is on the next must
    # not make its future label visible to a training split.
    usable["target_date"] = _kst_naive(usable["target_at"]).dt.date.astype(str)
    dates = sorted(usable["target_date"].unique())
    if len(usable) < MIN_LABELED_ROWS or len(dates) < MIN_COHORT_DAYS:
        return pd.DataFrame(), {
            "skipped": True,
            "reason": "insufficient labeled rows or calendar days for score evaluation",
            "labeled_rows": int(len(usable)),
            "calendar_days": int(len(dates)),
        }
    cut = max(1, int(len(dates) * 0.8))
    train_dates, test_dates = set(dates[:cut]), set(dates[cut:])
    train = usable[
        usable["date"].isin(train_dates) & usable["target_date"].isin(train_dates)
    ].copy()
    test = usable[
        usable["date"].isin(test_dates) & usable["target_date"].isin(test_dates)
    ].copy()
    if len(test) < MIN_TEST_ROWS or len(test_dates) < MIN_TEST_DAYS:
        return pd.DataFrame(), {
            "skipped": True,
            "reason": "insufficient time-separated test rows or test days",
            "labeled_rows": int(len(usable)),
            "test_rows": int(len(test)),
            "test_days": int(len(test_dates)),
        }
    try:
        from sklearn.linear_model import LogisticRegression  # noqa: PLC0415
        from sklearn.preprocessing import StandardScaler  # noqa: PLC0415
    except ImportError:
        return pd.DataFrame(), {
            "skipped": True,
            "reason": "scikit-learn unavailable; cannot fit leakage-safe comparison",
            "labeled_rows": int(len(usable)),
        }

    base_cols = ["available_binary_at_t", "total_chargers_at_t", "hour", "weekday"]
    parking_cols = [*base_cols, "occupancy_rate", "remaining_spaces"]
    y_train, y_test = train["target_available"].astype(int).to_numpy(), test["target_available"].astype(int).to_numpy()
    if len(np.unique(y_train)) < 2 or len(np.unique(y_test)) < 2:
        return pd.DataFrame(), {
            "skipped": True,
            "reason": "single-class target in train or time-separated test set",
            "labeled_rows": int(len(usable)),
        }

    def predict(columns: list[str]) -> np.ndarray:
        scaler = StandardScaler()
        x_train = train[columns].fillna(train[columns].median()).fillna(0).to_numpy()
        x_test = test[columns].fillna(train[columns].median()).fillna(0).to_numpy()
        return LogisticRegression(max_iter=500, random_state=RANDOM_SEED).fit(
            scaler.fit_transform(x_train), y_train
        ).predict_proba(scaler.transform(x_test))[:, 1]

    p_base, p_parking = predict(base_cols), predict(parking_cols)
    metrics = pd.DataFrame(
        [_metric_row("baseline_status_time", y_test, p_base), _metric_row("plus_team5_parking", y_test, p_parking)]
    )
    delta = _metric_row("parking_minus_baseline", y_test, p_parking)
    for metric in ("auroc", "pr_auc", "brier"):
        delta[metric] = (
            float(metrics.loc[1, metric] - metrics.loc[0, metric])
            if pd.notna(metrics.loc[1, metric]) and pd.notna(metrics.loc[0, metric])
            else None
        )
    delta["n_test"] = int(len(test))
    metrics = pd.concat([metrics, pd.DataFrame([delta])], ignore_index=True)

    rng = np.random.default_rng(RANDOM_SEED)
    station_ids = test["station_id"].dropna().unique()
    samples: list[dict[str, float]] = []
    if len(station_ids) >= MIN_BOOTSTRAP_STATIONS:
        test_eval = test.assign(p_base=p_base, p_parking=p_parking)
        for _ in range(300):
            chosen = rng.choice(station_ids, size=len(station_ids), replace=True)
            sample = pd.concat([test_eval[test_eval["station_id"].eq(s)] for s in chosen], ignore_index=True)
            y = sample["target_available"].astype(int).to_numpy()
            row = {}
            for metric, func in (
                ("auroc_delta", _auc),
                ("pr_auc_delta", _pr_auc),
            ):
                left, right = func(y, sample["p_base"].to_numpy()), func(y, sample["p_parking"].to_numpy())
                if left is not None and right is not None:
                    row[metric] = right - left
            row["brier_delta"] = float(
                np.mean((y - sample["p_parking"].to_numpy()) ** 2)
                - np.mean((y - sample["p_base"].to_numpy()) ** 2)
            )
            samples.append(row)
    ci = {}
    for key in ("auroc_delta", "pr_auc_delta", "brier_delta"):
        values = pd.DataFrame(samples).get(key, pd.Series(dtype=float)).dropna()
        ci[key] = (
            {"low": float(values.quantile(0.025)), "high": float(values.quantile(0.975)), "n": int(len(values))}
            if not values.empty
            else None
        )
    return metrics, {
        "skipped": False,
        "labeled_rows": int(len(usable)),
        "train_dates": sorted(train_dates),
        "test_dates": sorted(test_dates),
        "test_rows": int(len(test)),
        "test_stations": int(len(station_ids)),
        "bootstrap_ci": ci,
    }


def _plot_inventory(cohort: pd.DataFrame, out: Path) -> Path | None:
    if plt is None:
        return None
    fig, ax = plt.subplots(figsize=(8, 4.5), facecolor="#f7f8fa")
    _style(ax)
    labels = ["STRONG\nstation", "status\nrows", "time-aligned\nparking", "future\nlabels 15m"]
    values = [
        int(cohort["station_id"].nunique()) if not cohort.empty else 0,
        int(len(cohort)),
        int(cohort["parking_realtime_at_t"].sum()) if not cohort.empty else 0,
        int(cohort.get("target_available", pd.Series(dtype=float)).notna().sum()) if not cohort.empty else 0,
    ]
    bars = ax.bar(labels, values, color=["#18794e", "#4c78a8", "#f58518", "#e45756"])
    for bar, value in zip(bars, values, strict=True):
        ax.text(bar.get_x() + bar.get_width() / 2, value + max(values, default=1) * 0.02, f"{value:,}", ha="center")
    ax.set_title("점수 검증에 실제로 쓸 수 있는 표본", loc="left", fontweight="bold")
    ax.set_ylabel("행 또는 충전소 수")
    path = out / "01_validation_cohort_funnel.png"
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return path


def _plot_lag(cohort: pd.DataFrame, out: Path) -> Path | None:
    if plt is None:
        return None
    values = cohort.loc[cohort["parking_lag_minutes"].notna(), "parking_lag_minutes"]
    if values.empty:
        return None
    fig, ax = plt.subplots(figsize=(8, 4.5), facecolor="#f7f8fa")
    _style(ax)
    ax.hist(values, bins=min(20, max(5, values.nunique())), color="#4c78a8")
    ax.axvline(MAX_PARKING_STATUS_LAG_MIN, color="#e45756", linestyle="--", label="허용 최대 시차")
    ax.set_title("충전 상태 ↔ Team5 주차 관측 시차", loc="left", fontweight="bold")
    ax.set_xlabel("주차 관측이 앞선 시간 (분)")
    ax.set_ylabel("상태 행 수")
    ax.legend(frameon=False)
    path = out / "02_parking_status_lag.png"
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return path


def _write_readme(out: Path, summary: dict[str, object], metrics: pd.DataFrame, figures: list[Path]) -> None:
    decision = summary["decision"]
    inventory = summary["inventory"]
    def count(value: object) -> str:
        return f"{int(value):,}" if value is not None else "N/A"

    metric_text = (
        _markdown_table(metrics)
        if not metrics.empty
        else "_성능 비교를 실행하지 않음: 표본/시간 게이트 미달 또는 모델 실행 환경 미충족_"
    )
    figure_text = "\n".join(f"![{p.stem}](figures/{p.name})" for p in figures)
    text = f"""# Team5 주차 데이터 — 추천 점수 반영 검증

| 항목 | 값 |
|---|---|
| 생성 시각 | {summary["generated_at_kst"]} |
| 판정 | **{decision["verdict"]}** |
| 추천 점수 반영 | **{decision["include_in_score"]}** |
| 결론 | {decision["reason"]} |

## 판정 범위

- KOTSA 부분 추출본과 1km 근접 주차장 조인은 점수 입력에서 제외했다.
- `STRONG` 공존 후보만 사용했으며, 주차 관측은 충전 상태보다 최대 {MAX_PARKING_STATUS_LAG_MIN}분 이전인 값만 허용했다.
- 목표는 현재 상태가 아니라 `t+15분`의 사용 가능 충전기 존재 여부다. 미래 상태·ETA·추천 점수는 입력에 넣지 않았다.
- 이 검증은 실제 사용자의 도착·충전 성공 라벨이 없으므로, 그 라벨을 대체하지 않는다.

## 데이터 인벤토리

| 지표 | 값 |
|---|---:|
| 상태 이벤트 행 | {count(inventory["status_event_rows"])} |
| 상태 panel 행 | {count(inventory["status_panel_rows"])} |
| 상태 기간 일수 | {count(inventory["status_days"])} |
| Team5 realtime 행 | {count(inventory["parking_rows"])} |
| Team5 기간 일수 | {count(inventory["parking_days"])} |
| STRONG 공존 충전소 | {count(inventory["strong_stations"])} |
| STRONG cohort 상태 행 | {count(inventory["cohort_rows"])} |
| 시간 동기화 주차 행 | {count(inventory["aligned_parking_rows"])} |
| t+15 미래 라벨 행 | {count(inventory["labeled_rows_15m"])} |
| 주차 동기화 t+15 라벨 행 | {count(inventory["aligned_labeled_rows_15m"])} |

## 성능 비교

{metric_text}

## 점수 반영 게이트

| 게이트 | 기준 | 결과 |
|---|---|---|
| 공간 확정성 | STRONG 공존 충전소 ≥ {MIN_COHORT_STATIONS} | {decision["gates"]["cohort_stations"]} |
| 시간 성숙도 | 동기화 주차 이력 ≥ {MIN_COHORT_DAYS}일 | {decision["gates"]["calendar_days"]} |
| 미래 라벨 | 주차 동기화 t+15 라벨 ≥ {MIN_LABELED_ROWS} | {decision["gates"]["labeled_rows"]} |
| 시간 분리 검증 | 테스트 ≥ {MIN_TEST_ROWS}행·{MIN_TEST_DAYS}일 | {decision["gates"]["time_split"]} |
| 성능 개선 | bootstrap 신뢰구간상 기준 모델보다 개선 | {decision["gates"]["performance"]} |

## 제품 처리

{decision["product_action"]}

## 산출물

- `summary.json`: 기계판독 판정과 입력 범위
- `cohort_15m.csv`: STRONG cohort와 주차 동기화·미래 라벨 플래그 (분석 재현용)
- `metrics.csv`: 기준 모델/주차 추가 모델 비교 (가능한 경우)
- `strong_pairs_used.csv`: 이번 검증에서 사용한 공간 후보

## 그림

{figure_text}
"""
    (out / "README.md").write_text(text, encoding="utf-8")


def main() -> int:
    stamp = datetime.now(KST).strftime("%Y%m%d")
    out = REPO / "docs/data/analysis" / f"parking_score_validation_{stamp}"
    fig = out / "figures"
    if out.exists():
        shutil.rmtree(out)
    fig.mkdir(parents=True)

    parking, parking_sources = _load_parking_history()
    pairs = _strong_pairs()
    stations = _station_panel()
    cohort = _build_cohort(stations, parking, pairs)
    labeled_15 = _future_labels(cohort, 15)
    metrics, evaluation = _fit_and_compare(labeled_15)

    inventory = {
        "status_event_rows": None,
        "status_panel_rows": int(len(stations)),
        "status_days": int(stations["status_at"].dt.date.nunique()) if not stations.empty else 0,
        "parking_rows": int(len(parking)),
        "parking_days": int(parking["collected_at"].dt.date.nunique()) if not parking.empty else 0,
        "strong_stations": int(pairs["station_id"].nunique()),
        "cohort_rows": int(len(cohort)),
        "cohort_stations": int(cohort["station_id"].nunique()) if not cohort.empty else 0,
        "aligned_parking_rows": int(cohort["parking_realtime_at_t"].sum()) if not cohort.empty else 0,
        "labeled_rows_15m": int(labeled_15["target_available"].notna().sum()) if not labeled_15.empty else 0,
        "aligned_labeled_rows_15m": int(
            (labeled_15["parking_realtime_at_t"] & labeled_15["target_available"].notna()).sum()
        )
        if not labeled_15.empty
        else 0,
        "parking_sources": parking_sources,
    }
    ci = (evaluation.get("bootstrap_ci") or {}).get("auroc_delta") if not evaluation.get("skipped") else None
    performance_pass = bool(ci and ci["low"] > 0)
    enough_stations = inventory["cohort_stations"] >= MIN_COHORT_STATIONS
    enough_days = inventory["parking_days"] >= MIN_COHORT_DAYS
    enough_labels = inventory["aligned_labeled_rows_15m"] >= MIN_LABELED_ROWS
    time_split = not bool(evaluation.get("skipped"))
    score_pass = all((enough_stations, enough_days, enough_labels, time_split, performance_pass))
    failed = []
    if not enough_stations:
        failed.append("STRONG 공존 cohort 수 부족")
    if not enough_days:
        failed.append("Team5 시간 이력 14일 미달")
    if not enough_labels:
        failed.append("t+15 미래 라벨 수 부족")
    if not time_split:
        failed.append(str(evaluation.get("reason", "시간 분리 모델 검증 미실행")))
    if time_split and not performance_pass:
        failed.append("주차 추가 모델의 AUROC 개선 신뢰구간이 0 초과가 아님")
    decision = {
        "verdict": "PARKING_SCORE_CANDIDATE" if score_pass else "PARKING_AUXILIARY_ONLY",
        "include_in_score": bool(score_pass),
        "reason": (
            "모든 공간·시간·성능 게이트 통과"
            if score_pass
            else "점수 반영 근거 부족: " + "; ".join(failed)
        ),
        "product_action": (
            "주차 피처는 합의된 범위에서만 점수 후보로 제안할 수 있다."
            if score_pass
            else "주차 잔여면·점유율은 추천 점수와 순위에 반영하지 않는다. "
            "검증된 공존 후보의 보조 안내 문구로만 표시한다."
        ),
        "gates": {
            "cohort_stations": "PASS" if enough_stations else "FAIL",
            "calendar_days": "PASS" if enough_days else "FAIL",
            "labeled_rows": "PASS" if enough_labels else "FAIL",
            "time_split": "PASS" if time_split else "FAIL",
            "performance": "PASS" if performance_pass else "FAIL",
        },
    }
    figures = [path for path in [_plot_inventory(labeled_15, fig)] if path is not None]
    lag = _plot_lag(cohort, fig)
    if lag:
        figures.append(lag)

    pairs.to_csv(out / "strong_pairs_used.csv", index=False, encoding="utf-8-sig")
    labeled_15.to_csv(out / "cohort_15m.csv", index=False, encoding="utf-8-sig")
    metrics.to_csv(out / "metrics.csv", index=False, encoding="utf-8-sig")
    summary: dict[str, object] = {
        "generated_at_kst": datetime.now(KST).isoformat(timespec="seconds"),
        "scope": {
            "parking_source": "Team5 realtime only",
            "excluded": ["KOTSA partial/static extract", "1km nearby parking join"],
            "colocation_requirement": "STRONG only",
            "max_parking_status_lag_minutes": MAX_PARKING_STATUS_LAG_MIN,
            "target": "station has >=1 available charger at t+15m",
        },
        "inventory": inventory,
        "evaluation": evaluation,
        "decision": decision,
        "artifacts": {
            "strong_pairs": "strong_pairs_used.csv",
            "cohort": "cohort_15m.csv",
            "metrics": "metrics.csv",
            "report": "README.md",
        },
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_readme(out, summary, metrics, figures)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"OUT {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
