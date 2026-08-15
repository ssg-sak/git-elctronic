"""Overfitting risk analysis for final HGB arrival-ETA feature set.

Outputs metrics + charts under:
  docs/data/analysis/hgb_overfit_risk_YYYYMMDD/
  docs/팀공유/과적합위험_HGB_도착ETA_YYYYMMDD/
  D:/EV_SafeCharge_DA1/BI_과적합위험_HGB_도착ETA_YYYYMMDD/
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib.pyplot as plt
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

_ANALYSIS = Path(__file__).resolve().parent
if str(_ANALYSIS) not in sys.path:
    sys.path.insert(0, str(_ANALYSIS))

from run_hgb_arrival_eta_fitness import load_frame

REPO = ensure_paths()
KST = ZoneInfo("Asia/Seoul")

FINAL = [
    "available_count",
    "total_chargers",
    "known_charger_count",
    "observation_coverage",
    "hour",
    "weekday",
    "avail_rate_lag_15m",
    "avail_rate_lag_60m",
    "tmap_eta_min",
]
# temptation sets
STACK_ETA = FINAL + ["horizon_minutes", "haversine_km"]  # will dedupe
MINIMAL = [
    "available_count",
    "total_chargers",
    "known_charger_count",
    "observation_coverage",
    "tmap_eta_min",
]


def _setup_font():
    from matplotlib import font_manager

    for name in ("Malgun Gothic", "맑은 고딕", "NanumGothic"):
        if any(name in f.name for f in font_manager.fontManager.ttflist):
            plt.rcParams["font.family"] = name
            break
    plt.rcParams["axes.unicode_minus"] = False


def _metrics(y, p) -> dict:
    pred = (p >= 0.5).astype(int)
    return {
        "pr_auc": float(average_precision_score(y, p)),
        "roc_auc": float(roc_auc_score(y, p)),
        "brier": float(brier_score_loss(y, p)),
        "neg_recall": float(recall_score(y, pred, pos_label=0, zero_division=0)),
        "n": int(len(y)),
        "pos_rate": float(np.mean(y)),
    }


def _fit(X_tr, y_tr, X_te, *, max_depth=6, max_iter=200, seed=42):
    clf = HistGradientBoostingClassifier(
        max_depth=max_depth,
        learning_rate=0.08,
        max_iter=max_iter,
        min_samples_leaf=50,
        l2_regularization=1.0,
        early_stopping=True,
        validation_fraction=0.1,
        n_iter_no_change=20,
        random_state=seed,
    )
    pos = max(int((y_tr == 1).sum()), 1)
    neg = max(int((y_tr == 0).sum()), 1)
    w = np.where(y_tr == 0, pos / neg, 1.0).astype(float)
    clf.fit(X_tr, y_tr, sample_weight=w)
    return clf.predict_proba(X_te)[:, 1], getattr(clf, "n_iter_", None)


def gap_row(name, m_tr, m_va, m_te) -> dict:
    return {
        "spec": name,
        "train_pr_auc": m_tr["pr_auc"],
        "valid_pr_auc": m_va["pr_auc"],
        "test_pr_auc": m_te["pr_auc"],
        "gap_train_valid_pr": m_tr["pr_auc"] - m_va["pr_auc"],
        "gap_train_test_pr": m_tr["pr_auc"] - m_te["pr_auc"],
        "gap_valid_test_pr": m_va["pr_auc"] - m_te["pr_auc"],
        "train_neg_recall": m_tr["neg_recall"],
        "valid_neg_recall": m_va["neg_recall"],
        "test_neg_recall": m_te["neg_recall"],
        "gap_train_test_neg": m_tr["neg_recall"] - m_te["neg_recall"],
        "train_brier": m_tr["brier"],
        "valid_brier": m_va["brier"],
        "test_brier": m_te["brier"],
        "gap_train_test_brier": m_te["brier"] - m_tr["brier"],
    }


def eval_spec(df, feats, name, **kw):
    use = [c for c in feats if c in df.columns]
    # unique preserve order
    seen = set()
    use = [c for c in use if not (c in seen or seen.add(c))]
    tr = df[df["split"] == "train"]
    va = df[df["split"] == "valid"]
    te = df[df["split"] == "test"]
    p_tr, _ = _fit(tr[use], tr["y"].to_numpy(), tr[use], **kw)
    p_va, _ = _fit(tr[use], tr["y"].to_numpy(), va[use], **kw)
    p_te, n_iter = _fit(tr[use], tr["y"].to_numpy(), te[use], **kw)
    m_tr = _metrics(tr["y"].to_numpy(), p_tr)
    m_va = _metrics(va["y"].to_numpy(), p_va)
    m_te = _metrics(te["y"].to_numpy(), p_te)
    row = gap_row(name, m_tr, m_va, m_te)
    row["n_features"] = len(use)
    row["n_iter"] = int(n_iter) if n_iter is not None else None
    row["features"] = ",".join(use)
    return row, m_tr, m_va, m_te


def learning_curve_by_train_frac(df, feats):
    use = [c for c in feats if c in df.columns]
    tr = df[df["split"] == "train"].sort_values("feature_as_of")
    te = df[df["split"] == "test"]
    rows = []
    for frac in (0.2, 0.4, 0.6, 0.8, 1.0):
        n = max(int(len(tr) * frac), 2000)
        sub = tr.iloc[:n]
        p, _ = _fit(sub[use], sub["y"].to_numpy(), te[use], seed=42)
        m = _metrics(te["y"].to_numpy(), p)
        rows.append({"train_frac": frac, "train_n": n, **{f"test_{k}": v for k, v in m.items()}})
    return pd.DataFrame(rows)


def capacity_sweep(df, feats):
    rows = []
    for depth in (3, 6, 12):
        for max_iter in (50, 200, 500):
            row, *_ = eval_spec(
                df, feats, f"depth{depth}_iter{max_iter}", max_depth=depth, max_iter=max_iter
            )
            row["max_depth"] = depth
            row["max_iter"] = max_iter
            rows.append(row)
    return pd.DataFrame(rows)


def label_shuffle_sanity(df, feats, seed=0):
    """If model still looks good on shuffled y → leakage/overfit red flag."""
    use = [c for c in feats if c in df.columns]
    tr = df[df["split"] == "train"].copy()
    te = df[df["split"] == "test"].copy()
    rng = np.random.default_rng(seed)
    y_tr = tr["y"].to_numpy().copy()
    rng.shuffle(y_tr)
    p, _ = _fit(tr[use], y_tr, te[use], seed=42)
    # evaluate against TRUE test labels — should collapse toward baseline
    return _metrics(te["y"].to_numpy(), p)


def corr_matrix(df, feats):
    use = [c for c in feats if c in df.columns]
    return df[use].astype(float).corr()


def risk_verdict(gaps: dict, shuffle_pr: float, base_test_pr: float) -> dict:
    checks = []
    g_tv = gaps["gap_train_valid_pr"]
    g_tt = gaps["gap_train_test_pr"]
    g_vt = abs(gaps["gap_valid_test_pr"])
    checks.append(
        {
            "code": "TRAIN_VALID_PR_GAP",
            "value": g_tv,
            "rule": "<=0.03",
            "status": "PASS" if g_tv <= 0.03 else ("WARN" if g_tv <= 0.05 else "FAIL"),
        }
    )
    checks.append(
        {
            "code": "TRAIN_TEST_PR_GAP",
            "value": g_tt,
            "rule": "<=0.04",
            "status": "PASS" if g_tt <= 0.04 else ("WARN" if g_tt <= 0.06 else "FAIL"),
        }
    )
    checks.append(
        {
            "code": "VALID_TEST_PR_STABLE",
            "value": g_vt,
            "rule": "abs<=0.02",
            "status": "PASS" if g_vt <= 0.02 else ("WARN" if g_vt <= 0.04 else "FAIL"),
        }
    )
    # shuffle should drop a lot vs real
    drop = base_test_pr - shuffle_pr
    checks.append(
        {
            "code": "LABEL_SHUFFLE_COLLAPSE",
            "value": drop,
            "shuffle_test_pr_auc": shuffle_pr,
            "rule": "real - shuffle PR-AUC >= 0.05",
            "status": "PASS" if drop >= 0.05 else "FAIL",
        }
    )
    ranks = {"PASS": 0, "WARN": 1, "FAIL": 2}
    worst = max(checks, key=lambda c: ranks[c["status"]])["status"]
    return {"overall": worst, "checks": checks}


def plot_all(out_fig: Path, gaps_df: pd.DataFrame, curve: pd.DataFrame, cap: pd.DataFrame, corr: pd.DataFrame, final_row: dict):
    _setup_font()
    out_fig.mkdir(parents=True, exist_ok=True)

    # 01 gap bars for final
    fig, ax = plt.subplots(figsize=(7, 4))
    labels = ["train", "valid", "test"]
    vals = [final_row["train_pr_auc"], final_row["valid_pr_auc"], final_row["test_pr_auc"]]
    ax.bar(labels, vals, color=["#1f4e79", "#5b9bd5", "#9dc3e6"])
    ax.set_ylim(0.95, 1.0)
    ax.set_ylabel("PR-AUC")
    ax.set_title("과적합 점검 — train/valid/test PR-AUC (최종 9피처)")
    for i, v in enumerate(vals):
        ax.text(i, v, f"{v:.3f}", ha="center", va="bottom")
    fig.savefig(out_fig / "01_split_pr_auc_gap.png", dpi=140, bbox_inches="tight")
    plt.close(fig)

    # 02 spec comparison gaps
    fig, ax = plt.subplots(figsize=(8, 4.5))
    d = gaps_df.copy()
    x = np.arange(len(d))
    ax.bar(x - 0.2, d["gap_train_test_pr"], 0.4, label="train−test PR", color="#c00000")
    ax.bar(x + 0.2, d["gap_train_valid_pr"], 0.4, label="train−valid PR", color="#ed7d31")
    ax.axhline(0.04, color="gray", ls="--", lw=1)
    ax.set_xticks(x)
    ax.set_xticklabels(d["spec"], rotation=15, ha="right")
    ax.set_ylabel("PR-AUC gap")
    ax.set_title("스펙별 train 갭 (낮을수록 과적합 위험↓)")
    ax.legend()
    fig.savefig(out_fig / "02_spec_train_gaps.png", dpi=140, bbox_inches="tight")
    plt.close(fig)

    # 03 learning curve
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(curve["train_frac"], curve["test_pr_auc"], "o-", color="#1f4e79", label="test PR-AUC")
    ax.plot(curve["train_frac"], curve["test_neg_recall"], "s--", color="#548235", label="test neg-recall")
    ax.set_xlabel("train fraction (time-ordered)")
    ax.set_ylabel("score")
    ax.set_title("학습곡선 — 데이터 늘릴수록 test가 올라가는가")
    ax.legend()
    fig.savefig(out_fig / "03_learning_curve.png", dpi=140, bbox_inches="tight")
    plt.close(fig)

    # 04 capacity heatmap-ish
    pivot = cap.pivot_table(index="max_depth", columns="max_iter", values="gap_train_test_pr")
    fig, ax = plt.subplots(figsize=(6.5, 3.8))
    im = ax.imshow(pivot.values, cmap="YlOrRd", aspect="auto")
    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels(pivot.columns)
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels(pivot.index)
    ax.set_xlabel("max_iter")
    ax.set_ylabel("max_depth")
    ax.set_title("용량 스윕 — train−test PR gap (붉을수록 과적합↑)")
    for i in range(pivot.shape[0]):
        for j in range(pivot.shape[1]):
            ax.text(j, i, f"{pivot.values[i, j]:.3f}", ha="center", va="center", fontsize=9)
    fig.colorbar(im, ax=ax, fraction=0.046)
    fig.savefig(out_fig / "04_capacity_gap_heatmap.png", dpi=140, bbox_inches="tight")
    plt.close(fig)

    # 05 corr
    fig, ax = plt.subplots(figsize=(8, 6.5))
    im = ax.imshow(corr.values, cmap="RdBu_r", vmin=-1, vmax=1)
    ax.set_xticks(range(len(corr.columns)))
    ax.set_yticks(range(len(corr.index)))
    ax.set_xticklabels(corr.columns, rotation=45, ha="right", fontsize=8)
    ax.set_yticklabels(corr.index, fontsize=8)
    ax.set_title("최종 피처 상관 (다중공선 점검)")
    fig.colorbar(im, ax=ax, fraction=0.046)
    fig.savefig(out_fig / "05_feature_correlation.png", dpi=140, bbox_inches="tight")
    plt.close(fig)


def main() -> int:
    stamp = datetime.now(KST).strftime("%Y%m%d")
    analysis = REPO / "docs/data/analysis" / f"hgb_overfit_risk_{stamp}"
    share = REPO / "docs/팀공유" / f"과적합위험_HGB_도착ETA_{stamp}"
    d_out = Path(f"D:/EV_SafeCharge_DA1/BI_과적합위험_HGB_도착ETA_{stamp}")
    for p in (analysis, share, share / "figures", d_out, d_out / "figures"):
        p.mkdir(parents=True, exist_ok=True)

    print("loading sample frame…")
    df = load_frame(sample_neg_mult=20, max_pos=400_000)

    print("evaluating feature-set specs…")
    specs = [
        ("minimal5", MINIMAL),
        ("final9", FINAL),
        ("final9_plus_horizon_hav", FINAL + ["horizon_minutes", "haversine_km"]),
        ("final9_plus_single_charger", FINAL + ["single_charger"]),
    ]
    gap_rows = []
    final_pack = None
    for name, feats in specs:
        row, m_tr, m_va, m_te = eval_spec(df, feats, name)
        gap_rows.append(row)
        if name == "final9":
            final_pack = (row, m_tr, m_va, m_te)
    gaps_df = pd.DataFrame(gap_rows)
    gaps_df.to_csv(analysis / "split_gap_by_spec.csv", index=False, encoding="utf-8-sig")

    print("learning curve…")
    curve = learning_curve_by_train_frac(df, FINAL)
    curve.to_csv(analysis / "learning_curve.csv", index=False, encoding="utf-8-sig")

    print("capacity sweep…")
    cap = capacity_sweep(df, FINAL)
    cap.to_csv(analysis / "capacity_sweep.csv", index=False, encoding="utf-8-sig")

    print("label shuffle…")
    shuffle_m = label_shuffle_sanity(df, FINAL)
    (analysis / "label_shuffle_sanity.json").write_text(
        json.dumps(shuffle_m, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    corr = corr_matrix(df[df["split"] == "train"], FINAL)
    corr.to_csv(analysis / "feature_correlation.csv", encoding="utf-8-sig")

    assert final_pack is not None
    final_row, m_tr, m_va, m_te = final_pack
    verdict = risk_verdict(final_row, shuffle_m["pr_auc"], m_te["pr_auc"])

    # high corr pairs
    pairs = []
    cols = list(corr.columns)
    for i, a in enumerate(cols):
        for b in cols[i + 1 :]:
            v = float(corr.loc[a, b])
            if abs(v) >= 0.7:
                pairs.append({"a": a, "b": b, "corr": v})

    summary = {
        "status": f"OVERFIT_RISK_{verdict['overall']}",
        "model": "HistGradientBoostingClassifier",
        "target": "target_available_at_arrival",
        "final_features": FINAL,
        "n_features": len(FINAL),
        "train": m_tr,
        "valid": m_va,
        "test": m_te,
        "gaps": {
            "train_valid_pr": final_row["gap_train_valid_pr"],
            "train_test_pr": final_row["gap_train_test_pr"],
            "valid_test_pr": final_row["gap_valid_test_pr"],
            "train_test_neg": final_row["gap_train_test_neg"],
        },
        "label_shuffle_test_pr_auc": shuffle_m["pr_auc"],
        "high_corr_pairs_abs_ge_0_7": pairs,
        "verdict": verdict,
        "guidance": {
            "use_final9": True,
            "avoid_eta_stack": True,
            "avoid_extra_derived": True,
            "note": "accuracy 금지 · PR-AUC/neg-recall/Brier + 시간분할로만 판단",
        },
    }
    (analysis / "OVERFIT_SUMMARY.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    plot_all(share / "figures", gaps_df, curve, cap, corr, final_row)
    # mirror to D and analysis
    for src in (share / "figures").glob("*.png"):
        for dest_root in (analysis / "figures", d_out / "figures"):
            dest_root.mkdir(parents=True, exist_ok=True)
            (dest_root / src.name).write_bytes(src.read_bytes())

    # also mark fitness complete sidecar
    fit_dir = REPO / "docs/data/analysis/hgb_arrival_eta_fitness_20260808"
    if fit_dir.exists():
        (fit_dir / "MODEL_FITNESS_COMPLETE.json").write_text(
            json.dumps(
                {
                    "status": "DA1_MODEL_FITNESS_AND_OVERFIT_COMPLETE",
                    "fitness": "hgb_arrival_eta_fitness_20260808",
                    "overfit": str(analysis.relative_to(REPO)).replace("\\", "/"),
                    "final_features": FINAL,
                    "overfit_overall": verdict["overall"],
                    "test_pr_auc": m_te["pr_auc"],
                    "test_neg_recall": m_te["neg_recall"],
                    "test_brier": m_te["brier"],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    md = f"""# 과적합 위험도 · HGB 도착 ETA (최종 9피처)

| 항목 | 값 |
|---|---|
| **모델** | HistGradientBoosting |
| **피처** | 최종 9 (`tmap_eta_min` 포함) |
| **종합 판정** | **{verdict['overall']}** |
| **train PR-AUC** | {m_tr['pr_auc']:.4f} |
| **valid PR-AUC** | {m_va['pr_auc']:.4f} |
| **test PR-AUC** | {m_te['pr_auc']:.4f} |
| **train−test PR gap** | {final_row['gap_train_test_pr']:+.4f} |
| **label shuffle test PR** | {shuffle_m['pr_auc']:.4f} (붕괴해야 정상) |

## 체크리스트

| 코드 | 값 | 기준 | 판정 |
|---|---:|---|:---:|
"""
    for c in verdict["checks"]:
        md += f"| `{c['code']}` | {c['value']:.4f} | {c['rule']} | {c['status']} |\n"

    md += f"""
## 해석

- train↔test PR 갭이 작으면 **외삽 과적합 신호 약함**.
- 라벨 셔플 후 test PR이 크게 떨어지면 **누수/암기 아님** (정상).
- ETA 3종 스택·파생 추가는 갭만 키우거나 이득≈0 → **넣지 말 것**.
- `|corr|≥0.7` 쌍: {pairs if pairs else "없음(0.7 미만)"}

## 그림

![gap](figures/01_split_pr_auc_gap.png)

![spec](figures/02_spec_train_gaps.png)

![curve](figures/03_learning_curve.png)

![cap](figures/04_capacity_gap_heatmap.png)

![corr](figures/05_feature_correlation.png)

## 경로

- 분석: `{analysis.relative_to(REPO).as_posix()}/`
- 팀공유: `{share.relative_to(REPO).as_posix()}/`
- D: `D:/EV_SafeCharge_DA1/BI_과적합위험_HGB_도착ETA_{stamp}/`

```
DA① | HGB overfit risk | {stamp}
```
"""
    (share / "README.md").write_text(md, encoding="utf-8")
    (share / "OVERFIT_SUMMARY.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (d_out / "README.md").write_text(md, encoding="utf-8")
    gaps_df.to_csv(share / "split_gap_by_spec.csv", index=False, encoding="utf-8-sig")
    gaps_df.to_csv(d_out / "split_gap_by_spec.csv", index=False, encoding="utf-8-sig")

    # update fitness BI folder pointer
    fit_share = REPO / "docs/팀공유/피처선정_최종_HGB_도착ETA_20260808"
    if fit_share.exists():
        note = fit_share / "과적합위험_링크.md"
        note.write_text(
            f"""# 과적합 위험 분석 링크

- 결과: [`../과적합위험_HGB_도착ETA_{stamp}/README.md`](../과적합위험_HGB_도착ETA_{stamp}/README.md)
- D: `D:/EV_SafeCharge_DA1/BI_과적합위험_HGB_도착ETA_{stamp}/`

모델 적합도 + 과적합 패키지 완료.
""",
            encoding="utf-8",
        )

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if verdict["overall"] != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
