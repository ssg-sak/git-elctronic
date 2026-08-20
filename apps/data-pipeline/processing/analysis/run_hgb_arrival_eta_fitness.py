"""HGB fitness on arrival ETA labels (DA① handoff evidence).

Uses confirmed model family: HistGradientBoostingClassifier.
Target: target_available_at_arrival from arrival_labels_tmap_eta_v1_with_derived.
Does NOT choose serving scores — reports PR-AUC / neg-recall / Brier + ablation.

Usage:
  python apps/data-pipeline/processing/analysis/run_hgb_arrival_eta_fitness.py
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    recall_score,
    roc_auc_score,
)

_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))
from _bootstrap import ensure_paths

REPO = ensure_paths()
KST = ZoneInfo("Asia/Seoul")

LABELS = (
    REPO
    / "apps/data-pipeline/evaluation/results/datasets"
    / "arrival_labels_tmap_eta_v1_with_derived.parquet"
)
PANEL = (
    REPO
    / "apps/data-pipeline/evaluation/results/datasets"
    / "station_feature_panel_latest.parquet"
)

# MVP_v1-compatible + derived_v0 (labels-native / panel-joinable)
BASE_FEATURES = [
    "available_count",
    "total_chargers",
    "known_charger_count",
    "observation_coverage",
    "avail_ratio_t0",
    "single_charger",
    "hour",
    "weekday",
    "is_weekend",
    "avail_rate_lag_15m",
    "avail_rate_lag_60m",
]
# 택1 ETA family — default keep horizon; ablate alternatives
ETA_FAMILY = ["horizon_minutes", "tmap_eta_min", "haversine_km"]
# never train on
EXCLUDE_ALWAYS = {"eta_is_proxy", "eta_bucket"}  # bucket via one-hot optional; default off


def _metrics(y_true: np.ndarray, proba: np.ndarray) -> dict[str, float]:
    y = y_true.astype(int)
    pred = (proba >= 0.5).astype(int)
    out = {
        "pr_auc": float(average_precision_score(y, proba)),
        "roc_auc": float(roc_auc_score(y, proba)) if len(np.unique(y)) > 1 else float("nan"),
        "brier": float(brier_score_loss(y, proba)),
        "neg_recall": float(recall_score(y, pred, pos_label=0, zero_division=0)),
        "pos_rate": float(y.mean()),
        "n": int(len(y)),
    }
    return out


def _fit_predict(
    X_tr: pd.DataFrame,
    y_tr: np.ndarray,
    X_te: pd.DataFrame,
    *,
    seed: int = 42,
) -> np.ndarray:
    clf = HistGradientBoostingClassifier(
        max_depth=6,
        learning_rate=0.08,
        max_iter=200,
        min_samples_leaf=50,
        l2_regularization=1.0,
        early_stopping=True,
        validation_fraction=0.1,
        n_iter_no_change=20,
        random_state=seed,
    )
    # class imbalance: emphasize negatives via sample_weight
    pos = max(int((y_tr == 1).sum()), 1)
    neg = max(int((y_tr == 0).sum()), 1)
    w = np.where(y_tr == 0, pos / neg, 1.0).astype(float)
    clf.fit(X_tr, y_tr, sample_weight=w)
    return clf.predict_proba(X_te)[:, 1]


def _time_split(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    dates = out["feature_date"].sort_values().unique()
    n = len(dates)
    if n < 6:
        # fallback by row order quantiles
        q = out["feature_as_of"].rank(method="first") / len(out)
        out["split"] = np.where(q <= 0.70, "train", np.where(q <= 0.85, "valid", "test"))
        return out
    i_tr = dates[int(n * 0.70)]
    i_va = dates[int(n * 0.85)]
    out["split"] = np.where(
        out["feature_date"] <= i_tr,
        "train",
        np.where(out["feature_date"] <= i_va, "valid", "test"),
    )
    return out


def load_frame(sample_neg_mult: int = 20, max_pos: int = 400_000) -> pd.DataFrame:
    lab = pd.read_parquet(LABELS)
    lab["statId"] = lab["statId"].astype(str)
    lab["feature_as_of"] = pd.to_datetime(lab["feature_as_of"])
    lab["feature_date"] = lab["feature_as_of"].dt.floor("D")
    lab["available_count"] = pd.to_numeric(
        lab["current_available_count"], errors="coerce"
    )
    lab["total_chargers"] = pd.to_numeric(lab["total_chargers"], errors="coerce")
    lab["horizon_minutes"] = pd.to_numeric(lab["horizon_minutes"], errors="coerce")
    lab["tmap_eta_min"] = pd.to_numeric(lab["tmap_eta_min"], errors="coerce")
    lab["haversine_km"] = pd.to_numeric(lab["haversine_km"], errors="coerce")
    lab["single_charger"] = pd.to_numeric(lab["single_charger"], errors="coerce")
    lab["avail_ratio_t0"] = pd.to_numeric(lab["avail_ratio_t0"], errors="coerce")
    lab["y"] = lab["target_available_at_arrival"].astype(int)
    lab["hour"] = lab["feature_as_of"].dt.hour.astype(int)
    lab["weekday"] = lab["feature_as_of"].dt.weekday.astype(int)
    lab["is_weekend"] = (lab["weekday"] >= 5).astype(int)

    panel = pd.read_parquet(
        PANEL,
        columns=[
            "statId",
            "panel_ts",
            "known_chargers",
            "usable_known",
            "availability_ratio_observed",
            "avail_rate_lag_15m",
            "avail_rate_lag_60m",
        ],
    )
    panel["statId"] = panel["statId"].astype(str)
    panel["panel_ts"] = pd.to_datetime(panel["panel_ts"])
    panel = panel.rename(
        columns={
            "panel_ts": "feature_as_of",
            "known_chargers": "known_charger_count",
        }
    )
    merged = lab.merge(panel, on=["statId", "feature_as_of"], how="left")
    merged["observation_coverage"] = (
        pd.to_numeric(merged["known_charger_count"], errors="coerce")
        / pd.to_numeric(merged["total_chargers"], errors="coerce")
    ).clip(0, 1)

    # class-balanced sample for fit speed (keep ALL negatives)
    rng = np.random.default_rng(42)
    neg_idx = merged.index[merged["y"] == 0].to_numpy()
    pos_idx = merged.index[merged["y"] == 1].to_numpy()
    n_pos = min(len(pos_idx), max(len(neg_idx) * sample_neg_mult, 50_000), max_pos)
    keep = np.concatenate(
        [neg_idx, rng.choice(pos_idx, size=n_pos, replace=False)]
    )
    sample = merged.loc[keep].copy()
    return _time_split(sample)


def univariate(df: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    train = df[df["split"] == "train"]
    rows = []
    for f in features:
        x = pd.to_numeric(train[f], errors="coerce")
        y = train["y"]
        m = x.notna()
        row: dict[str, Any] = {
            "feature": f,
            "null_rate": float(1 - m.mean()),
            "distinct": int(x[m].nunique()),
            "directional_auc": None,
            "pr_auc_univ": None,
        }
        if m.sum() < 500 or y[m].nunique() < 2 or x[m].nunique() < 2:
            rows.append(row)
            continue
        try:
            auc = float(roc_auc_score(y[m], x[m]))
            row["directional_auc"] = max(auc, 1.0 - auc)
        except Exception:  # noqa: BLE001
            pass
        try:
            # orient so higher score ≈ positive if corr positive
            corr = np.corrcoef(x[m].astype(float), y[m].astype(float))[0, 1]
            score = x[m].astype(float) if corr >= 0 else -x[m].astype(float)
            row["pr_auc_univ"] = float(average_precision_score(y[m], score))
        except Exception:  # noqa: BLE001
            pass
        rows.append(row)
    return pd.DataFrame(rows)


def run_hgb_suite(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    train = df[df["split"] == "train"]
    valid = df[df["split"] == "valid"]
    test = df[df["split"] == "test"]

    default_feats = BASE_FEATURES + ["horizon_minutes"]
    # drop HOLD diagnostic from default MVP if desired — keep for ablation baseline A
    specs: list[tuple[str, list[str]]] = [
        ("A_mvp_horizon", [c for c in default_feats if c != "avail_ratio_t0"]),
        ("A_plus_avail_ratio", default_feats),
        ("B_mvp_tmap_eta", [c for c in BASE_FEATURES if c != "avail_ratio_t0"] + ["tmap_eta_min"]),
        ("C_mvp_haversine", [c for c in BASE_FEATURES if c != "avail_ratio_t0"] + ["haversine_km"]),
        ("D_horizon_only_eta_family", [c for c in BASE_FEATURES if c != "avail_ratio_t0"]
         + ["horizon_minutes", "tmap_eta_min", "haversine_km"]),
    ]
    # leave-one-out on recommended set
    core = [c for c in default_feats if c != "avail_ratio_t0"]
    for drop in core:
        specs.append((f"LOO_drop_{drop}", [c for c in core if c != drop]))

    rows = []
    best: dict[str, Any] | None = None
    for name, feats in specs:
        use = [f for f in feats if f in df.columns]
        if len(use) < 2:
            continue
        X_tr, y_tr = train[use], train["y"].to_numpy()
        X_va, y_va = valid[use], valid["y"].to_numpy()
        X_te, y_te = test[use], test["y"].to_numpy()
        # drop rows with all-null in any required? HGB handles NaN
        try:
            p_va = _fit_predict(X_tr, y_tr, X_va)
            p_te = _fit_predict(X_tr, y_tr, X_te)
        except Exception as exc:  # noqa: BLE001
            rows.append({"spec": name, "features": ",".join(use), "error": str(exc)})
            continue
        m_va = _metrics(y_va, p_va)
        m_te = _metrics(y_te, p_te)
        rec = {
            "spec": name,
            "n_features": len(use),
            "features": ",".join(use),
            **{f"valid_{k}": v for k, v in m_va.items()},
            **{f"test_{k}": v for k, v in m_te.items()},
        }
        rows.append(rec)
        score = (m_va["pr_auc"], m_va["neg_recall"], -m_va["brier"])
        if best is None or score > best["_score"]:
            best = {**rec, "_score": score, "model": "HistGradientBoostingClassifier"}

    assert best is not None
    best.pop("_score", None)
    return pd.DataFrame(rows), best


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample-neg-mult", type=int, default=20)
    parser.add_argument("--max-pos", type=int, default=400_000)
    args = parser.parse_args()

    stamp = datetime.now(KST).strftime("%Y%m%d")
    report = REPO / "docs/data/analysis" / f"hgb_arrival_eta_fitness_{stamp}"
    share = REPO / "docs/팀공유" / f"피처적합도_HGB_도착ETA_{stamp}"
    report.mkdir(parents=True, exist_ok=True)
    share.mkdir(parents=True, exist_ok=True)

    print("loading labels+panel…")
    df = load_frame(sample_neg_mult=args.sample_neg_mult, max_pos=args.max_pos)
    print(
        f"sample rows={len(df)} pos_rate={df['y'].mean():.4f} "
        f"splits={df['split'].value_counts().to_dict()}"
    )

    feat_all = [c for c in BASE_FEATURES + ETA_FAMILY if c in df.columns]
    assoc = univariate(df, feat_all)
    assoc.to_csv(report / "feature_target_association.csv", index=False, encoding="utf-8-sig")

    print("fitting HGB suite…")
    abl, best = run_hgb_suite(df)
    abl.to_csv(report / "feature_ablation_metrics.csv", index=False, encoding="utf-8-sig")

    decisions = []
    for _, r in assoc.iterrows():
        f = str(r["feature"])
        auc = r.get("directional_auc")
        if f == "eta_is_proxy":
            dec, reason = "EXCLUDE_TRAINING", "quota/selection bias; stratify only"
        elif f == "avail_ratio_t0":
            dec, reason = "HOLD", "weak; ablation-only"
        elif f in {"horizon_minutes", "single_charger", "available_count", "total_chargers"}:
            dec, reason = "RETAIN", "MVP / derived_v0"
        elif f in {"tmap_eta_min", "haversine_km"}:
            dec, reason = "RETAIN_ALT", "택1 with horizon — do not stack all three"
        elif f in {"avail_rate_lag_15m", "avail_rate_lag_60m"}:
            dec, reason = "RETAIN_FOR_ABLATION", "panel lag; keep if LOO hurts"
        elif auc is not None and float(auc) >= 0.55:
            dec, reason = "RETAIN_CANDIDATE", "univariate AUC"
        else:
            dec, reason = "HOLD_FOR_HGB", "weak univariate; see ablation"
        decisions.append(
            {
                "feature": f,
                "decision": dec,
                "reason": reason,
                "directional_auc": None if pd.isna(auc) else float(auc),
                "null_rate": float(r["null_rate"]) if pd.notna(r["null_rate"]) else None,
            }
        )
    (report / "feature_selection_decisions.json").write_text(
        json.dumps(
            {
                "status": "HGB_ARRIVAL_ETA_FITNESS_COMPLETE",
                "model_family": "HistGradientBoostingClassifier",
                "target": "target_available_at_arrival",
                "decisions": decisions,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    profile = {
        "rows_sampled": int(len(df)),
        "stations": int(df["statId"].nunique()),
        "pos_rate_sampled": float(df["y"].mean()),
        "feature_as_of_min": str(df["feature_as_of"].min()),
        "feature_as_of_max": str(df["feature_as_of"].max()),
        "split_counts": df["split"].value_counts().to_dict(),
        "eta_is_proxy_rate": float(df["eta_is_proxy"].mean())
        if "eta_is_proxy" in df.columns
        else None,
        "labels": str(LABELS.relative_to(REPO)).replace("\\", "/"),
        "panel": str(PANEL.relative_to(REPO)).replace("\\", "/"),
        "note": "negatives kept in full; positives subsampled for fit speed",
    }
    (report / "training_dataset_profile.json").write_text(
        json.dumps(profile, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )

    summary = {
        "status": "DA1_HGB_ARRIVAL_ETA_FITNESS_READY",
        "model_family": "HistGradientBoostingClassifier",
        "target": "target_available_at_arrival",
        "report_dir": str(report.relative_to(REPO)).replace("\\", "/"),
        "best_valid_spec": best.get("spec"),
        "best_valid_pr_auc": best.get("valid_pr_auc"),
        "best_valid_neg_recall": best.get("valid_neg_recall"),
        "best_valid_brier": best.get("valid_brier"),
        "best_test_pr_auc": best.get("test_pr_auc"),
        "best_test_neg_recall": best.get("test_neg_recall"),
        "best_test_brier": best.get("test_brier"),
        "recommended_features": best.get("features"),
        "contract": {
            "accuracy_forbidden": True,
            "primary_metrics": ["pr_auc", "neg_recall", "brier"],
            "eta_family_pick_one": True,
            "eta_is_proxy_train": False,
            "serving_eta": "backend TMAP for final 3~5",
        },
        "profile": profile,
    }
    (report / "HANDOFF_SUMMARY.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # team-readable
    md = [
        "# HGB 적합도 — 도착 ETA 라벨 (2026-08-08)",
        "",
        "| 항목 | 값 |",
        "|---|---|",
        "| **모델** | HistGradientBoosting (확정 기준) |",
        "| **타겟** | `target_available_at_arrival` |",
        f"| **샘플** | {profile['rows_sampled']:,}행 · 양성률 {profile['pos_rate_sampled']:.3f} |",
        f"| **구간** | {profile['feature_as_of_min']} ~ {profile['feature_as_of_max']} |",
        f"| **권장 spec** | `{best.get('spec')}` |",
        f"| **valid PR-AUC** | {best.get('valid_pr_auc')} |",
        f"| **valid neg-recall** | {best.get('valid_neg_recall')} |",
        f"| **valid Brier** | {best.get('valid_brier')} |",
        f"| **test PR-AUC** | {best.get('test_pr_auc')} |",
        "",
        "## 권장 피처",
        "",
        "```",
        str(best.get("features")),
        "```",
        "",
        "## 산출",
        "",
        f"- `{report.relative_to(REPO).as_posix()}/`",
        "- 지표: PR-AUC / negative recall / Brier (accuracy 금지)",
        "- `eta_is_proxy` 학습 입력 금지 · ETA family는 horizon|tmap_eta|haversine 택1",
        "",
        "```",
        "DA① | HGB arrival-ETA fitness | 20260808",
        "```",
        "",
    ]
    (share / "README.md").write_text("\n".join(md), encoding="utf-8")
    abl.to_csv(share / "feature_ablation_metrics.csv", index=False, encoding="utf-8-sig")
    assoc.to_csv(share / "feature_target_association.csv", index=False, encoding="utf-8-sig")
    (share / "HANDOFF_SUMMARY.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
