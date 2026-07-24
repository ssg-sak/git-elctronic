"""Time-ordered backtest for ETA 15m — only if enough labeled rows."""
from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd

from .paths import OUT_FIGURES, OUT_JSON, OUT_TABLES, ensure_out

MIN_LABELED = 500
MIN_TEST = 50


def _safe_prob(p: np.ndarray) -> np.ndarray:
    return np.clip(p, 1e-6, 1 - 1e-6)


def _brier(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def _logloss(y: np.ndarray, p: np.ndarray) -> float:
    p = _safe_prob(p)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def _pr_auc(y: np.ndarray, p: np.ndarray) -> float | None:
    try:
        from sklearn.metrics import average_precision_score

        if len(np.unique(y)) < 2:
            return None
        return float(average_precision_score(y, p))
    except Exception:
        return None


def _precision_recall(y: np.ndarray, p: np.ndarray, thr: float = 0.5) -> tuple[float, float]:
    pred = (p >= thr).astype(int)
    tp = int(((pred == 1) & (y == 1)).sum())
    fp = int(((pred == 1) & (y == 0)).sum())
    fn = int(((pred == 0) & (y == 1)).sum())
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    return prec, rec


def _hit_ndcg_at_k(df: pd.DataFrame, score_col: str, k: int = 5) -> dict[str, float]:
    """Per timestamp: rank stations by score; Hit@k / NDCG@k vs label=1."""
    hits = []
    ndcgs = []
    for _, g in df.groupby("t"):
        if g["y"].sum() <= 0:
            continue
        g = g.sort_values(score_col, ascending=False).head(k)
        hit = float(g["y"].max() >= 1)
        # DCG
        rel = g["y"].to_numpy()
        gains = (2**rel - 1) / np.log2(np.arange(2, len(rel) + 2))
        dcg = float(gains.sum())
        ideal = np.sort(g["y"].to_numpy())[::-1]
        # use all positives in group for ideal — approximate with top-k ideal of this subset
        idcg = float(((2**ideal - 1) / np.log2(np.arange(2, len(ideal) + 2))).sum())
        ndcg = dcg / idcg if idcg > 0 else 0.0
        hits.append(hit)
        ndcgs.append(ndcg)
    return {
        "hit_at_5": float(np.mean(hits)) if hits else None,
        "ndcg_at_5": float(np.mean(ndcgs)) if ndcgs else None,
        "n_rank_groups": len(hits),
    }


def run_backtest(eta15_path: str | None = None) -> dict[str, Any]:
    ensure_out()
    from pathlib import Path as _P

    path = _P(eta15_path) if eta15_path else OUT_TABLES / "eta_targets_15m.csv"
    if not path.exists():
        return {"ok": False, "skipped": True, "reason": "eta_targets_15m.csv missing"}

    raw = pd.read_csv(path)
    lab = raw[raw["target_available"].notna()].copy()
    lab["y"] = lab["target_available"].astype(int)
    lab["t"] = pd.to_datetime(lab["t"])
    lab["available_observed_at_t"] = pd.to_numeric(lab["available_observed_at_t"], errors="coerce").fillna(0)

    if len(lab) < MIN_LABELED:
        return {
            "ok": False,
            "skipped": True,
            "reason": f"labeled rows {len(lab)} < {MIN_LABELED} — ML backtest not justified",
            "labeled_rows": int(len(lab)),
            "baselines_only_note": "Still report persistence baseline on available labels if ≥50",
        }

    dates = sorted(lab["date"].unique())
    n = len(dates)
    train_dates = set(dates[: max(1, int(n * 0.6))])
    valid_dates = set(dates[max(1, int(n * 0.6)) : max(1, int(n * 0.8))])
    test_dates = set(dates[max(1, int(n * 0.8)) :])
    if not test_dates:
        test_dates = set(dates[-1:])
        train_dates = set(dates[:-1])

    train = lab[lab["date"].isin(train_dates)]
    valid = lab[lab["date"].isin(valid_dates)] if valid_dates else train.iloc[0:0]
    test = lab[lab["date"].isin(test_dates)]
    if len(test) < MIN_TEST:
        return {
            "ok": False,
            "skipped": True,
            "reason": f"test labeled rows {len(test)} < {MIN_TEST}",
            "labeled_rows": int(len(lab)),
            "split": {"train": list(train_dates), "valid": list(valid_dates), "test": list(test_dates)},
        }

    # Features at t only (no future leak)
    # 1) persistence: P(available soon) ≈ 1 if currently observed available
    test = test.copy()
    test["p_persist"] = (test["available_observed_at_t"] >= 1).astype(float)

    # 2) station×weekday×hour historical rate from TRAIN only
    train = train.copy()
    train["weekday"] = train["t"].dt.weekday
    test["weekday"] = test["t"].dt.weekday
    hist = (
        train.groupby(["station_id", "weekday", "hour"])["y"]
        .mean()
        .rename("p_hist")
        .reset_index()
    )
    global_rate = float(train["y"].mean())
    test = test.merge(hist, on=["station_id", "weekday", "hour"], how="left")
    test["p_hist"] = test["p_hist"].fillna(global_rate)

    # 3) rule proxy: same as persistence (no separate validated score file for ETA)
    test["p_rule"] = test["p_persist"]

    # 4) logistic / 5) tree if sklearn available
    model_scores: dict[str, Any] = {}
    y_te = test["y"].to_numpy()

    def pack(name: str, p: np.ndarray) -> dict[str, Any]:
        prec, rec = _precision_recall(y_te, p)
        rank = _hit_ndcg_at_k(test.assign(score=p), "score", 5)
        return {
            "model": name,
            "n_test": int(len(test)),
            "brier": _brier(y_te, p),
            "logloss": _logloss(y_te, p),
            "precision": prec,
            "recall": rec,
            "pr_auc": _pr_auc(y_te, p),
            **rank,
            "coverage_labeled": 1.0,
            "note": "probabilities are model scores on labeled subset only — not calibrated claim",
        }

    results = [
        pack("persistence_current_available", test["p_persist"].to_numpy()),
        pack("station_dow_hour_hist", test["p_hist"].to_numpy()),
        pack("rule_proxy_eq_persistence", test["p_rule"].to_numpy()),
    ]

    try:
        from sklearn.linear_model import LogisticRegression
        from sklearn.preprocessing import StandardScaler

        # leak check: features only from t
        feat_cols = ["available_observed_at_t", "observed_chargers_at_t", "hour", "weekday"]
        train["weekday"] = train["t"].dt.weekday
        Xtr = train[feat_cols].fillna(0).to_numpy()
        ytr = train["y"].to_numpy()
        Xte = test[feat_cols].fillna(0).to_numpy()
        scaler = StandardScaler()
        Xtr_s = scaler.fit_transform(Xtr)
        Xte_s = scaler.transform(Xte)
        lr = LogisticRegression(max_iter=500)
        lr.fit(Xtr_s, ytr)
        p_lr = lr.predict_proba(Xte_s)[:, 1]
        test["p_lr"] = p_lr
        results.append(pack("logistic_regression", p_lr))
        model_scores["logistic"] = True
    except Exception as exc:  # noqa: BLE001
        model_scores["logistic_error"] = str(exc)

    try:
        from sklearn.ensemble import GradientBoostingClassifier

        feat_cols = ["available_observed_at_t", "observed_chargers_at_t", "hour", "weekday"]
        Xtr = train[feat_cols].fillna(0).to_numpy()
        ytr = train["y"].to_numpy()
        Xte = test[feat_cols].fillna(0).to_numpy()
        gb = GradientBoostingClassifier(random_state=42)
        gb.fit(Xtr, ytr)
        p_gb = gb.predict_proba(Xte)[:, 1]
        test["p_gb"] = p_gb
        results.append(pack("sklearn_gradient_boosting", p_gb))
        model_scores["gbdt"] = True
    except Exception as exc:  # noqa: BLE001
        model_scores["gbdt_error"] = str(exc)

    # calibration plot for best brier among ML
    try:
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(5, 5))
        for name, col in [("persist", "p_persist"), ("hist", "p_hist")]:
            if col not in test.columns:
                continue
            bins = np.linspace(0, 1, 6)
            test["_bin"] = pd.cut(test[col], bins, include_lowest=True)
            cal = test.groupby("_bin", observed=False).agg(p=(col, "mean"), y=("y", "mean"))
            ax.plot(cal["p"], cal["y"], marker="o", label=name)
        ax.plot([0, 1], [0, 1], "k--", lw=1)
        ax.set_xlabel("predicted")
        ax.set_ylabel("empirical")
        ax.set_title("Reliability (labeled test only)")
        ax.legend()
        fig.tight_layout()
        fig.savefig(OUT_FIGURES / "calibration_eta15.png", dpi=120)
        plt.close(fig)
    except Exception as exc:  # noqa: BLE001
        model_scores["calib_error"] = str(exc)

    pd.DataFrame(results).to_csv(OUT_TABLES / "backtest_metrics.csv", index=False, encoding="utf-8-sig")

    # leakage checklist
    leakage = {
        "random_split_used": False,
        "temporal_split_used": True,
        "features_after_t": False,
        "rolling_uses_past_only": True,
        "target_uses_reconstruct_only": False,
        "null_targets_as_zero": False,
    }

    out = {
        "ok": True,
        "skipped": False,
        "labeled_rows": int(len(lab)),
        "split": {
            "train_dates": sorted(train_dates),
            "valid_dates": sorted(valid_dates),
            "test_dates": sorted(test_dates),
            "n_train": int(len(train)),
            "n_valid": int(len(valid)),
            "n_test": int(len(test)),
        },
        "metrics": results,
        "leakage_checks": leakage,
        "model_notes": model_scores,
        "interpretation": (
            "Compare Brier/PR-AUC vs persistence. If ML ≉ persistence, ETA signal may be weak "
            "or labels too sparse/biased by change-feed."
        ),
    }
    (OUT_JSON / "backtest.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    return out
