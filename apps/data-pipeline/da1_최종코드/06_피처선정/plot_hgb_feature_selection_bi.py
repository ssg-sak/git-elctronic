"""BI charts for HGB arrival-ETA final feature selection (easy view)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))
from _bootstrap import ensure_paths

REPO = ensure_paths()
ANALYSIS = REPO / "docs/data/analysis/hgb_arrival_eta_fitness_20260808"
SHARE = REPO / "docs/팀공유/피처선정_최종_HGB_도착ETA_20260808"
FIG = SHARE / "figures"
# D: principle — also mirror charts for local viewing
D_OUT = Path("D:/EV_SafeCharge_DA1/BI_피처선정_HGB_도착ETA_20260808")


def _setup():
    from matplotlib import font_manager

    for name in ("Malgun Gothic", "맑은 고딕", "NanumGothic", "AppleGothic"):
        if any(name in f.name for f in font_manager.fontManager.ttflist):
            plt.rcParams["font.family"] = name
            break
    plt.rcParams.update(
        {
            "axes.unicode_minus": False,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "axes.grid": True,
            "grid.alpha": 0.25,
            "font.size": 10,
            "axes.titlesize": 12,
            "axes.labelsize": 10,
        }
    )
    FIG.mkdir(parents=True, exist_ok=True)
    D_OUT.mkdir(parents=True, exist_ok=True)


def _save(fig, name: str):
    for root in (FIG, D_OUT / "figures"):
        root.mkdir(parents=True, exist_ok=True)
        fig.savefig(root / name, dpi=140, bbox_inches="tight")
    plt.close(fig)


def plot_spec_compare(abl: pd.DataFrame):
    specs = [
        "A_mvp_horizon",
        "B_mvp_tmap_eta",
        "C_mvp_haversine",
        "D_horizon_only_eta_family",
    ]
    d = abl[abl["spec"].isin(specs)].copy()
    d["label"] = d["spec"].map(
        {
            "A_mvp_horizon": "A horizon",
            "B_mvp_tmap_eta": "B tmap_eta\n(최종 ETA)",
            "C_mvp_haversine": "C haversine",
            "D_horizon_only_eta_family": "D 3종스택\n(비권장)",
        }
    )
    x = np.arange(len(d))
    w = 0.35
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.bar(x - w / 2, d["valid_pr_auc"], w, label="valid PR-AUC", color="#1f4e79")
    ax.bar(x + w / 2, d["test_pr_auc"], w, label="test PR-AUC", color="#5b9bd5")
    ax.set_xticks(x)
    ax.set_xticklabels(d["label"])
    ax.set_ylim(0.97, 0.99)
    ax.set_ylabel("PR-AUC")
    ax.set_title("HGB 스펙 비교 — PR-AUC (arrival ETA 라벨)")
    ax.legend()
    ax.axhline(0.98214, color="#c45911", ls="--", lw=1, label="최종(B) valid")
    _save(fig, "01_spec_pr_auc.png")

    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.bar(x - w / 2, d["valid_neg_recall"], w, label="valid neg-recall", color="#548235")
    ax.bar(x + w / 2, d["test_neg_recall"], w, label="test neg-recall", color="#a9d08e")
    ax.set_xticks(x)
    ax.set_xticklabels(d["label"])
    ax.set_ylim(0.80, 0.90)
    ax.set_ylabel("negative recall")
    ax.set_title("HGB 스펙 비교 — negative recall (실패 탐지)")
    ax.legend()
    _save(fig, "02_spec_neg_recall.png")


def plot_loo(abl: pd.DataFrame):
    base = abl.loc[abl["spec"] == "A_mvp_horizon"].iloc[0]
    loo = abl[abl["spec"].str.startswith("LOO_drop_")].copy()
    loo["dropped"] = loo["spec"].str.replace("LOO_drop_", "", regex=False)
    loo["d_pr"] = loo["valid_pr_auc"] - float(base["valid_pr_auc"])
    loo["d_neg"] = loo["valid_neg_recall"] - float(base["valid_neg_recall"])
    loo = loo.sort_values("d_pr")

    fig, ax = plt.subplots(figsize=(9, 5.5))
    colors = ["#c00000" if v < -0.001 else ("#7f7f7f" if abs(v) < 1e-6 else "#548235") for v in loo["d_pr"]]
    ax.barh(loo["dropped"], loo["d_pr"], color=colors)
    ax.axvline(0, color="black", lw=0.8)
    ax.set_xlabel("Δ valid PR-AUC (음수 = 빼면 성능↓ = 중요)")
    ax.set_title("Leave-one-out — 피처 제거 시 PR-AUC 변화")
    _save(fig, "03_loo_delta_pr_auc.png")

    fig, ax = plt.subplots(figsize=(9, 5.5))
    colors = ["#c00000" if v < -0.01 else ("#7f7f7f" if abs(v) < 1e-6 else "#548235") for v in loo["d_neg"]]
    ax.barh(loo["dropped"], loo["d_neg"], color=colors)
    ax.axvline(0, color="black", lw=0.8)
    ax.set_xlabel("Δ valid neg-recall")
    ax.set_title("Leave-one-out — 피처 제거 시 neg-recall 변화")
    _save(fig, "04_loo_delta_neg_recall.png")


def plot_univ(assoc: pd.DataFrame):
    d = assoc.sort_values("directional_auc", ascending=True)
    final = {
        "available_count",
        "total_chargers",
        "known_charger_count",
        "observation_coverage",
        "hour",
        "weekday",
        "avail_rate_lag_15m",
        "avail_rate_lag_60m",
        "tmap_eta_min",
    }
    colors = ["#1f4e79" if f in final else "#b0b0b0" for f in d["feature"]]
    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.barh(d["feature"], d["directional_auc"], color=colors)
    ax.axvline(0.55, color="#c45911", ls="--", lw=1)
    ax.set_xlabel("directional AUC")
    ax.set_title("단변량 변별력 (파랑=최종 RETAIN · 회색=탈락/비채택)")
    _save(fig, "05_univariate_auc.png")


def plot_reliability_blocks(blocks: pd.DataFrame):
    fig, ax = plt.subplots(figsize=(8, 4.2))
    labels = [f"B{int(r.block)}\n{str(r.date_min)[:10]}~{str(r.date_max)[5:10]}" for r in blocks.itertuples()]
    ax.plot(labels, blocks["pr_auc"], "o-", color="#1f4e79", label="PR-AUC")
    ax.plot(labels, blocks["neg_recall"], "s--", color="#548235", label="neg-recall")
    ax.set_ylim(0.65, 1.0)
    ax.set_ylabel("score")
    ax.set_title("신뢰도 — 시간 블록 CV (초반 블록만 낮음 → WARN)")
    ax.legend()
    _save(fig, "06_reliability_temporal_blocks.png")


def plot_dashboard_kpi(final: dict):
    te = final["final_test"]
    va = final["final_valid"]
    fig, axes = plt.subplots(1, 3, figsize=(10, 3.6))
    metrics = [
        ("PR-AUC", va["pr_auc"], te["pr_auc"], 0.95, 1.0),
        ("neg-recall", va["neg_recall"], te["neg_recall"], 0.7, 1.0),
        ("Brier↓", va["brier"], te["brier"], 0.0, 0.3),
    ]
    for ax, (name, v, t, ymin, ymax) in zip(axes, metrics):
        ax.bar(["valid", "test"], [v, t], color=["#1f4e79", "#5b9bd5"])
        ax.set_title(name)
        ax.set_ylim(ymin, ymax)
        for i, val in enumerate([v, t]):
            ax.text(i, val, f"{val:.3f}", ha="center", va="bottom", fontsize=9)
    fig.suptitle("최종 9피처 HGB — 핵심 지표 (accuracy 금지)", y=1.02)
    _save(fig, "00_kpi_final_set.png")


def plot_decision_cards():
    rows = [
        ("파생변수", "불필요", "#548235"),
        ("최종 피처", "9개 RETAIN", "#1f4e79"),
        ("ETA 택1", "tmap_eta_min", "#1f4e79"),
        ("타당도", "PASS", "#548235"),
        ("신뢰도", "WARN", "#c45911"),
        ("모델", "HGB 확정", "#1f4e79"),
    ]
    fig, axes = plt.subplots(2, 3, figsize=(10, 4.5))
    for ax, (title, val, color) in zip(axes.ravel(), rows):
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis("off")
        ax.add_patch(plt.Rectangle((0.05, 0.15), 0.9, 0.7, fill=False, ec=color, lw=2))
        ax.text(0.5, 0.62, title, ha="center", va="center", fontsize=11, color="#666")
        ax.text(0.5, 0.38, val, ha="center", va="center", fontsize=16, fontweight="bold", color=color)
    fig.suptitle("한눈에 보기 — HGB 도착ETA 피처 선정", fontsize=13)
    _save(fig, "07_decision_overview.png")


def write_dashboard_md(final: dict):
    md = f"""# HGB 피처 선정 BI 대시보드 (보기용)

| | |
|---|---|
| **모델** | HistGradientBoosting |
| **타겟** | `target_available_at_arrival` |
| **파생변수** | **불필요** |
| **최종 피처** | **9개** · ETA=`tmap_eta_min` |
| **타당도** | **PASS** · test PR-AUC {final['final_test']['pr_auc']:.3f} · neg-recall {final['final_test']['neg_recall']:.3f} |
| **신뢰도** | **WARN** (시간블록 CV만 경계 · valid/test·seed PASS) |
| **D: 복사** | `D:/EV_SafeCharge_DA1/BI_피처선정_HGB_도착ETA_20260808/` |

## 0. 한눈에

![overview](figures/07_decision_overview.png)

![kpi](figures/00_kpi_final_set.png)

## 1. 스펙 비교 (ETA 택1)

![pr](figures/01_spec_pr_auc.png)

![neg](figures/02_spec_neg_recall.png)

> B(`tmap_eta_min`)를 최종 ETA로 채택. D(3종 스택)는 소폭 우세하나 택1 계약·다중공선으로 비권장.

## 2. 피처 중요 (LOO)

![loo_pr](figures/03_loo_delta_pr_auc.png)

![loo_neg](figures/04_loo_delta_neg_recall.png)

> `available_count`·`horizon` 제거 시 타격 큼. `single_charger`·`is_weekend` 제거 시 Δ≈0 → 파생/중복 불필요.

## 3. 단변량 AUC

![univ](figures/05_univariate_auc.png)

## 4. 신뢰도 — 시간 블록

![block](figures/06_reliability_temporal_blocks.png)

> 초반(7/17–24)만 낮음. 피처 세트 붕괴 아님.

## 최종 RETAIN 9

1. available_count  
2. total_chargers  
3. known_charger_count  
4. observation_coverage  
5. hour  
6. weekday  
7. avail_rate_lag_15m  
8. avail_rate_lag_60m  
9. tmap_eta_min  

## 제외

`single_charger` · `eta_bucket` · `avail_ratio_t0` · `is_weekend` · `eta_is_proxy` · horizon/haversine(택1에서 탈락) · usage · 주차점수

```
DA① | HGB feature BI dashboard | 20260808
```
"""
    (SHARE / "BI_대시보드.md").write_text(md, encoding="utf-8")
    (D_OUT / "BI_대시보드.md").write_text(md, encoding="utf-8")
    # also refresh main README pointer
    readme = (SHARE / "README.md").read_text(encoding="utf-8")
    if "BI_대시보드.md" not in readme:
        readme = readme.replace(
            "## 산출 경로",
            "## 보기용 BI\n\n- **[`BI_대시보드.md`](./BI_대시보드.md)** ← 그림 모음\n- 그림: `figures/`\n- D: `D:/EV_SafeCharge_DA1/BI_피처선정_HGB_도착ETA_20260808/`\n\n## 산출 경로",
        )
        (SHARE / "README.md").write_text(readme, encoding="utf-8")


def main() -> int:
    _setup()
    abl = pd.read_csv(ANALYSIS / "feature_ablation_metrics.csv")
    assoc = pd.read_csv(ANALYSIS / "feature_target_association.csv")
    final = json.loads((ANALYSIS / "final_feature_selection.json").read_text(encoding="utf-8"))
    blocks = pd.read_csv(ANALYSIS / "reliability_temporal_blocks.csv")

    plot_decision_cards()
    plot_dashboard_kpi(final)
    plot_spec_compare(abl)
    plot_loo(abl)
    plot_univ(assoc)
    plot_reliability_blocks(blocks)
    write_dashboard_md(final)
    print(f"OUT {SHARE / 'figures'}")
    print(f"OUT {D_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
