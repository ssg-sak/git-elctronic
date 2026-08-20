"""Chart-type gallery for missing viz forms — using arrival-label / D1 data.

Produces team-share pack with violin, KDE, hexbin, pairplot, ECDF, QQ,
ROC/PR, confusion, stacked bar, errorbar, radar, waterfall, ridge-like,
parallel coordinates, treemap-ish, sankey-ish funnel.

Usage (repo root):
  python apps/data-pipeline/processing/analysis/plot_chart_type_gallery.py
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Rectangle
from scipy import stats
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    confusion_matrix,
    precision_recall_curve,
    roc_auc_score,
    roc_curve,
)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

REPO = Path(__file__).resolve().parents[4]
KST = ZoneInfo("Asia/Seoul")
OUT_DS = REPO / "apps/data-pipeline/evaluation/results/datasets"

plt.rcParams["font.family"] = ["Malgun Gothic", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
sns.set_theme(style="whitegrid", font="Malgun Gothic")


def _stamp() -> str:
    return datetime.now(KST).strftime("%Y%m%d")


def _load_sample(n_pos: int = 40_000, n_neg_mult: int = 8, seed: int = 42) -> pd.DataFrame:
    path = OUT_DS / "arrival_labels_tmap_eta_v1_with_derived.parquet"
    cols = [
        "statId",
        "target_available_at_arrival",
        "current_available_count",
        "horizon_minutes",
        "tmap_eta_min",
        "haversine_km",
        "single_charger",
        "total_chargers",
        "eta_bucket",
        "avail_ratio_t0",
    ]
    lab = pd.read_parquet(path, columns=cols)
    y = lab["target_available_at_arrival"].astype(bool)
    rng = np.random.default_rng(seed)
    neg = lab.index[~y].to_numpy()
    pos = lab.index[y].to_numpy()
    n_pos = min(n_pos, len(pos))
    n_neg = min(len(neg), max(n_pos // n_neg_mult, 5_000))
    idx = np.concatenate(
        [rng.choice(neg, size=n_neg, replace=False), rng.choice(pos, size=n_pos, replace=False)]
    )
    s = lab.loc[idx].copy()
    s["y"] = s["target_available_at_arrival"].astype(int)
    s["single_charger"] = s["single_charger"].fillna(0).astype(int)
    s["group"] = np.where(s["single_charger"] == 1, "단수", "복수")
    s["outcome"] = np.where(s["y"] == 1, "도착시가용", "도착시불가")
    return s


def _save(fig: plt.Figure, dest: Path, name: str) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / name
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def fig_violin(s: pd.DataFrame, dest: Path) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    sns.violinplot(
        data=s.sample(min(20_000, len(s)), random_state=1),
        x="group",
        y="horizon_minutes",
        hue="outcome",
        split=True,
        inner="quartile",
        ax=axes[0],
        palette=["#54a24b", "#e45756"],
    )
    axes[0].set_title("바이올린: ETA(분) × 단수/복수 × 도착결과")
    axes[0].set_xlabel("")
    axes[0].set_ylabel("horizon / ETA(분)")
    sns.violinplot(
        data=s.sample(min(20_000, len(s)), random_state=2),
        x="outcome",
        y="current_available_count",
        hue="outcome",
        ax=axes[1],
        palette=["#54a24b", "#e45756"],
        cut=0,
        legend=False,
    )
    axes[1].set_title("바이올린: 출발 가용대수 × 도착결과")
    axes[1].set_xlabel("")
    axes[1].set_ylabel("current_available_count")
    fig.suptitle("미사용 유형 · 바이올린", y=1.02, fontsize=12)
    return _save(fig, dest, "01_violin.png")


def fig_kde(s: pd.DataFrame, dest: Path) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for name, g in s.groupby("outcome"):
        sns.kdeplot(
            g["tmap_eta_min"].clip(0, 80),
            ax=axes[0],
            label=name,
            fill=True,
            alpha=0.35,
            linewidth=1.5,
        )
    axes[0].set_title("KDE: TMAP ETA 밀도")
    axes[0].set_xlabel("tmap_eta_min")
    axes[0].legend()
    for name, g in s.groupby("group"):
        v = g["avail_ratio_t0"].clip(0, 1).dropna()
        if v.nunique() < 2:
            continue
        sns.kdeplot(
            v,
            ax=axes[1],
            label=name,
            fill=True,
            alpha=0.35,
            linewidth=1.5,
            warn_singular=False,
        )
    axes[1].set_title("KDE: 가용비율 밀도 (단수/복수)")
    axes[1].set_xlabel("avail_ratio_t0")
    axes[1].legend()
    fig.suptitle("미사용 유형 · KDE 밀도", y=1.02, fontsize=12)
    return _save(fig, dest, "02_kde.png")


def fig_hexbin(s: pd.DataFrame, dest: Path) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    hb = axes[0].hexbin(
        s["haversine_km"].clip(0, 25),
        s["tmap_eta_min"].clip(0, 80),
        gridsize=35,
        cmap="YlGnBu",
        mincnt=1,
    )
    fig.colorbar(hb, ax=axes[0], label="건수")
    axes[0].set_xlabel("직선거리 km")
    axes[0].set_ylabel("TMAP ETA 분")
    axes[0].set_title("hexbin: 거리 × ETA")
    hb2 = axes[1].hexbin(
        s["current_available_count"].clip(0, 20),
        s["horizon_minutes"].clip(0, 80),
        gridsize=25,
        cmap="OrRd",
        mincnt=1,
    )
    fig.colorbar(hb2, ax=axes[1], label="건수")
    axes[1].set_xlabel("출발 가용대수")
    axes[1].set_ylabel("ETA 분")
    axes[1].set_title("hexbin: 가용 × ETA")
    fig.suptitle("미사용 유형 · hexbin", y=1.02, fontsize=12)
    return _save(fig, dest, "03_hexbin.png")


def fig_pairplot(s: pd.DataFrame, dest: Path) -> Path:
    cols = [
        "current_available_count",
        "total_chargers",
        "horizon_minutes",
        "haversine_km",
        "avail_ratio_t0",
    ]
    sub = s[cols + ["outcome"]].sample(min(2500, len(s)), random_state=3)
    g = sns.pairplot(
        sub,
        hue="outcome",
        corner=True,
        plot_kws={"s": 8, "alpha": 0.35},
        diag_kind="kde",
        palette=["#54a24b", "#e45756"],
    )
    g.fig.suptitle("미사용 유형 · pairplot (산점도 행렬)", y=1.02, fontsize=12)
    path = dest / "04_pairplot.png"
    dest.mkdir(parents=True, exist_ok=True)
    g.savefig(path, dpi=140, bbox_inches="tight")
    plt.close(g.fig)
    return path


def fig_ecdf(s: pd.DataFrame, dest: Path) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for name, g in s.groupby("outcome"):
        sns.ecdfplot(g["horizon_minutes"].clip(0, 100), ax=axes[0], label=name)
    axes[0].set_title("ECDF: ETA")
    axes[0].set_xlabel("horizon_minutes")
    axes[0].legend()
    for name, g in s.groupby("group"):
        sns.ecdfplot(g["current_available_count"].clip(0, 25), ax=axes[1], label=name)
    axes[1].set_title("ECDF: 출발 가용대수")
    axes[1].set_xlabel("current_available_count")
    axes[1].legend()
    fig.suptitle("미사용 유형 · ECDF 누적분포", y=1.02, fontsize=12)
    return _save(fig, dest, "05_ecdf.png")


def fig_qq(s: pd.DataFrame, dest: Path) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    for ax, col, title in (
        (axes[0], "tmap_eta_min", "QQ: TMAP ETA vs 정규"),
        (axes[1], "current_available_count", "QQ: 가용대수 vs 정규"),
    ):
        x = pd.to_numeric(s[col], errors="coerce").dropna()
        x = x[(x >= x.quantile(0.01)) & (x <= x.quantile(0.99))]
        stats.probplot(x.sample(min(5000, len(x)), random_state=4), dist="norm", plot=ax)
        ax.set_title(title)
    fig.suptitle("미사용 유형 · QQ플롯", y=1.02, fontsize=12)
    return _save(fig, dest, "06_qq.png")


def fig_roc_pr_confusion(s: pd.DataFrame, dest: Path) -> tuple[Path, Path, Path, dict]:
    feats = ["current_available_count", "total_chargers", "horizon_minutes", "haversine_km", "single_charger"]
    X = s[feats].astype(float)
    y = s["y"].astype(int)
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.3, random_state=7, stratify=y)
    sc = StandardScaler()
    Xtr_s = sc.fit_transform(Xtr)
    Xte_s = sc.transform(Xte)
    clf = LogisticRegression(max_iter=500, class_weight="balanced")
    clf.fit(Xtr_s, ytr)
    proba = clf.predict_proba(Xte_s)[:, 1]
    pred = (proba >= 0.5).astype(int)

    fpr, tpr, _ = roc_curve(yte, proba)
    prec, rec, _ = precision_recall_curve(yte, proba)
    auc = float(roc_auc_score(yte, proba))
    cm = confusion_matrix(yte, pred)

    fig, ax = plt.subplots(figsize=(5.2, 4.5))
    ax.plot(fpr, tpr, color="#4c78a8", lw=2, label=f"로지스틱 AUC={auc:.3f}")
    ax.plot([0, 1], [0, 1], "k--", lw=1)
    ax.set_xlabel("FPR")
    ax.set_ylabel("TPR")
    ax.set_title("ROC (간단 베이스라인 · DA① 진단용)")
    ax.legend()
    p_roc = _save(fig, dest, "07_roc.png")

    fig, ax = plt.subplots(figsize=(5.2, 4.5))
    ax.plot(rec, prec, color="#e45756", lw=2)
    ax.set_xlabel("Recall")
    ax.set_ylabel("Precision")
    ax.set_title("PR 곡선 (양성률 높음 → PR이 더 중요)")
    ax.set_ylim(0, 1.05)
    p_pr = _save(fig, dest, "08_pr.png")

    fig, ax = plt.subplots(figsize=(4.8, 4.2))
    sns.heatmap(
        cm,
        annot=True,
        fmt="d",
        cmap="Blues",
        xticklabels=["예측불가", "예측가용"],
        yticklabels=["실제불가", "실제거용"],
        ax=ax,
    )
    ax.set_title("혼동행렬 (threshold=0.5, balanced LR)")
    p_cm = _save(fig, dest, "09_confusion.png")
    meta = {
        "roc_auc": auc,
        "features": feats,
        "note": "Not production model — chart-type demo + weak baseline only",
        "test_pos_rate": float(yte.mean()),
    }
    return p_roc, p_pr, p_cm, meta


def fig_stacked_bar(s: pd.DataFrame, dest: Path) -> Path:
    s = s.copy()
    s["eta_band"] = pd.cut(
        s["horizon_minutes"],
        bins=[-0.1, 10, 20, 40, 200],
        labels=["0-10", "10-20", "20-40", "40+"],
    )
    ct = pd.crosstab(s["eta_band"], s["outcome"], normalize="index") * 100
    fig, ax = plt.subplots(figsize=(7, 4.2))
    ct.plot(kind="bar", stacked=True, ax=ax, color=["#e45756", "#54a24b"], rot=0)
    ax.set_ylabel("비율 %")
    ax.set_xlabel("ETA 구간")
    ax.set_title("스택 막대: ETA구간 × 도착결과 구성비")
    ax.legend(title="")
    return _save(fig, dest, "10_stacked_bar.png")


def fig_errorbar(s: pd.DataFrame, dest: Path) -> Path:
    g = (
        s.groupby("horizon_minutes", as_index=False)["y"]
        .agg(mean="mean", std="std", n="count")
        .query("n >= 30")
        .sort_values("horizon_minutes")
    )
    # bin for readability
    g["band"] = (g["horizon_minutes"] // 5) * 5
    gb = g.groupby("band").agg(mean=("mean", "mean"), std=("std", "mean"), n=("n", "sum")).reset_index()
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.errorbar(
        gb["band"],
        gb["mean"],
        yerr=gb["std"].fillna(0),
        fmt="o-",
        color="#4c78a8",
        ecolor="#9ecae1",
        capsize=3,
        lw=1.6,
    )
    ax.set_ylim(0.7, 1.02)
    ax.set_xlabel("ETA 분 (5분 버킷)")
    ax.set_ylabel("도착가용률 (mean±std)")
    ax.set_title("에러바: ETA별 도착가용률")
    return _save(fig, dest, "11_errorbar.png")


def fig_radar(s: pd.DataFrame, dest: Path) -> Path:
    # compare mean profiles: 도착가용 vs 불가 (scaled 0-1 within sample)
    cols = {
        "current_available_count": "가용대수",
        "total_chargers": "전체수",
        "horizon_minutes": "ETA",
        "haversine_km": "거리",
        "avail_ratio_t0": "가용비율",
        "single_charger": "단수비율",
    }
    # invert ETA/거리/단수 so "better" is outward for availability story? keep raw scaled
    prof = {}
    for outcome, label in ((1, "도착시가용"), (0, "도착시불가")):
        sub = s.loc[s["y"] == outcome, list(cols)]
        # min-max on full s for comparable axes
        scaled = []
        for c in cols:
            v = pd.to_numeric(s[c], errors="coerce")
            lo, hi = v.quantile(0.05), v.quantile(0.95)
            x = (sub[c].clip(lo, hi) - lo) / (hi - lo + 1e-9)
            scaled.append(float(x.mean()))
        prof[label] = scaled
    labels = list(cols.values())
    angles = np.linspace(0, 2 * np.pi, len(labels), endpoint=False).tolist()
    angles += angles[:1]
    fig, ax = plt.subplots(figsize=(5.5, 5.5), subplot_kw=dict(polar=True))
    for name, color in (("도착시가용", "#54a24b"), ("도착시불가", "#e45756")):
        vals = prof[name] + prof[name][:1]
        ax.plot(angles, vals, color=color, lw=2, label=name)
        ax.fill(angles, vals, color=color, alpha=0.15)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels)
    ax.set_title("레이더: 도착가용 vs 불가 평균 프로필", pad=16)
    ax.legend(loc="upper right", bbox_to_anchor=(1.25, 1.1))
    return _save(fig, dest, "12_radar.png")


def fig_waterfall(s: pd.DataFrame, dest: Path) -> Path:
    # candidate survival style waterfall from counts
    n = len(s)
    n_multi = int((s["single_charger"] == 0).sum())
    n_single = n - n_multi
    n_ok = int(s["y"].sum())
    n_fail = n - n_ok
    # steps relative to start
    steps = [
        ("샘플 전체", n),
        ("복수충전기", n_multi),
        ("단수충전기", n_single),
        ("도착가용", n_ok),
        ("도착불가", n_fail),
    ]
    # better: cumulative decomposition from all -> fail reasons proxy
    # All -> keep multi -> of multi success; show deltas
    values = [n, -n_single, -(n_multi - int(s.loc[s["single_charger"] == 0, "y"].sum())), -n_fail]
    # simpler absolute bars with connectors
    labels = ["①전체", "②복수만", "③복수·도착가용", "④전체·도착가용"]
    v2 = [
        n,
        n_multi,
        int(s.loc[s["single_charger"] == 0, "y"].sum()),
        n_ok,
    ]
    fig, ax = plt.subplots(figsize=(8, 4.2))
    colors = ["#4c78a8", "#72b7b2", "#54a24b", "#18794e"]
    x = np.arange(len(labels))
    ax.bar(x, v2, color=colors, width=0.65)
    for i in range(len(v2) - 1):
        ax.plot([i + 0.32, i + 1 - 0.32], [v2[i], v2[i + 1]], color="#888", lw=1)
    for i, v in enumerate(v2):
        ax.text(i, v, f"{v:,}", ha="center", va="bottom", fontsize=9)
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("행 수")
    ax.set_title("워터폴 느낌: 샘플 → 복수 → 도착가용 축소")
    return _save(fig, dest, "13_waterfall.png")


def fig_ridge(s: pd.DataFrame, dest: Path) -> Path:
    # ridge-like: KDE of ETA by eta_bucket stacked
    bands = ["0_10", "10_20", "20_40", "40p"]
    fig, axes = plt.subplots(len(bands), 1, figsize=(8, 6), sharex=True)
    colors = sns.color_palette("viridis", len(bands))
    for ax, band, c in zip(axes, bands, colors):
        sub = s.loc[s["eta_bucket"] == band, "current_available_count"].clip(0, 20)
        if len(sub) < 30:
            ax.set_visible(False)
            continue
        sns.kdeplot(sub, ax=ax, fill=True, color=c, alpha=0.7, linewidth=1)
        ax.set_ylabel(band, rotation=0, ha="right", va="center")
        ax.set_yticks([])
        ax.spines["left"].set_visible(False)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    axes[-1].set_xlabel("출발 가용대수")
    fig.suptitle("릿지(유사): ETA구간별 가용대수 밀도", y=0.98, fontsize=12)
    fig.tight_layout()
    return _save(fig, dest, "14_ridge.png")


def fig_parallel(s: pd.DataFrame, dest: Path) -> Path:
    cols = ["current_available_count", "total_chargers", "horizon_minutes", "haversine_km", "avail_ratio_t0"]
    sub = s.sample(min(400, len(s)), random_state=9).copy()
    # scale 0-1
    for c in cols:
        v = sub[c].astype(float)
        sub[c] = (v - v.min()) / (v.max() - v.min() + 1e-9)
    fig, ax = plt.subplots(figsize=(9, 4.5))
    x = np.arange(len(cols))
    for _, row in sub.iterrows():
        color = "#54a24b55" if row["y"] == 1 else "#e4575666"
        ax.plot(x, [row[c] for c in cols], color=color, lw=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(["가용", "전체", "ETA", "거리", "비율"], fontsize=10)
    ax.set_ylabel("정규화 0–1")
    ax.set_title("패러럴 코디네이트: 도착가용(녹) vs 불가(적) 샘플")
    return _save(fig, dest, "15_parallel.png")


def fig_treemap(s: pd.DataFrame, dest: Path) -> Path:
    # matplotlib treemap-ish rectangles by eta_bucket × outcome counts
    ct = s.groupby(["eta_bucket", "outcome"], dropna=False).size().reset_index(name="n")
    ct = ct.dropna(subset=["eta_bucket"])
    total = ct["n"].sum()
    # squarify-like simple row layout by bucket
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    buckets = [b for b in ["0_10", "10_20", "20_40", "40p"] if b in set(ct["eta_bucket"])]
    sizes = [ct.loc[ct["eta_bucket"] == b, "n"].sum() for b in buckets]
    sizes = np.array(sizes, dtype=float)
    sizes = sizes / sizes.sum()
    x0 = 0.0
    colors = {"도착시가용": "#54a24b", "도착시불가": "#e45756"}
    for b, w in zip(buckets, sizes):
        part = ct.loc[ct["eta_bucket"] == b]
        y0 = 0.0
        for _, r in part.iterrows():
            h = float(r["n"] / part["n"].sum())
            rect = Rectangle(
                (x0, y0),
                w * 0.98,
                h * 0.98,
                facecolor=colors.get(str(r["outcome"]), "#aaa"),
                edgecolor="white",
                linewidth=1.5,
            )
            ax.add_patch(rect)
            if w > 0.08 and h > 0.12:
                ax.text(
                    x0 + w * 0.49,
                    y0 + h * 0.49,
                    f"{b}\n{r['outcome']}\n{int(r['n']):,}",
                    ha="center",
                    va="center",
                    fontsize=8,
                    color="white",
                    fontweight="bold",
                )
            y0 += h
        x0 += w
    ax.set_title("트리맵(유사): ETA구간 × 도착결과 건수", fontsize=12, pad=8)
    return _save(fig, dest, "16_treemap.png")


def fig_sankey(s: pd.DataFrame, dest: Path) -> Path:
    # sankey-ish flow: group -> outcome
    fig, ax = plt.subplots(figsize=(8.5, 4.5))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.axis("off")
    left = {"단수": (1, 7.2), "복수": (1, 2.8)}
    right = {"도착시가용": (8.2, 7.0), "도착시불가": (8.2, 2.5)}
    flows = s.groupby(["group", "outcome"]).size().to_dict()
    total = sum(flows.values())
    # draw nodes
    for name, (x, y) in {**left, **right}.items():
        ax.add_patch(
            FancyBboxPatch(
                (x - 0.7, y - 0.55),
                1.6,
                1.1,
                boxstyle="round,pad=0.05,rounding_size=0.2",
                facecolor="#4c78a8" if name in left else "#72b7b2",
                edgecolor="white",
            )
        )
        ax.text(x + 0.1, y, name, ha="center", va="center", color="white", fontweight="bold")
    # flows as thick lines
    for (g, o), n in flows.items():
        x1, y1 = left[g]
        x2, y2 = right[o]
        lw = max(1.5, 18 * n / total)
        color = "#54a24a88" if o == "도착시가용" else "#e4575688"
        ax.annotate(
            "",
            xy=(x2 - 0.7, y2),
            xytext=(x1 + 0.9, y1),
            arrowprops=dict(arrowstyle="-", color=color, lw=lw, connectionstyle="arc3,rad=0.05"),
        )
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        ax.text(mx, my + 0.35, f"{n:,}", ha="center", fontsize=8, color="#333")
    ax.set_title("생키(유사): 단수/복수 → 도착 가용/불가", fontsize=12)
    return _save(fig, dest, "17_sankey.png")


def main() -> int:
    stamp = _stamp()
    analysis = REPO / "docs/data/analysis" / f"chart_type_gallery_{stamp}"
    share = REPO / "docs/팀공유" / f"차트유형_갤러리_{stamp}"
    fig_dir = share / "figures"
    analysis.mkdir(parents=True, exist_ok=True)
    fig_dir.mkdir(parents=True, exist_ok=True)

    print("loading sample…")
    s = _load_sample()
    print(f"sample n={len(s)} pos={s['y'].mean():.3f}")

    paths = []
    paths.append(fig_violin(s, fig_dir))
    paths.append(fig_kde(s, fig_dir))
    paths.append(fig_hexbin(s, fig_dir))
    paths.append(fig_pairplot(s, fig_dir))
    paths.append(fig_ecdf(s, fig_dir))
    paths.append(fig_qq(s, fig_dir))
    p_roc, p_pr, p_cm, ml_meta = fig_roc_pr_confusion(s, fig_dir)
    paths.extend([p_roc, p_pr, p_cm])
    paths.append(fig_stacked_bar(s, fig_dir))
    paths.append(fig_errorbar(s, fig_dir))
    paths.append(fig_radar(s, fig_dir))
    paths.append(fig_waterfall(s, fig_dir))
    paths.append(fig_ridge(s, fig_dir))
    paths.append(fig_parallel(s, fig_dir))
    paths.append(fig_treemap(s, fig_dir))
    paths.append(fig_sankey(s, fig_dir))

    meta = {
        "role": "DA① missing chart-type gallery",
        "as_of_kst": datetime.now(KST).isoformat(timespec="seconds"),
        "source": "arrival_labels_tmap_eta_v1_with_derived.parquet (sampled)",
        "sample_rows": int(len(s)),
        "sample_pos_rate": float(s["y"].mean()),
        "figures": [p.name for p in paths],
        "baseline_model": ml_meta,
        "caveat": [
            "Gallery for exploration/presentation — not new MVP features",
            "ROC/PR/confusion use a toy logistic baseline only",
            "Treemap/sankey/waterfall/ridge are matplotlib approximations",
        ],
    }
    (share / "summary.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (analysis / "summary.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (share / "README.md").write_text(
        f"""# 차트 유형 갤러리 — {stamp}

그동안 안 쓰던 차트 종류를 **도착 라벨(+derived_v0)** 샘플로 한 번 그려 본 팩입니다.

| # | 파일 | 유형 |
|---|---|---|
| 01 | `figures/01_violin.png` | 바이올린 |
| 02 | `figures/02_kde.png` | KDE 밀도 |
| 03 | `figures/03_hexbin.png` | hexbin |
| 04 | `figures/04_pairplot.png` | 산점도 행렬 |
| 05 | `figures/05_ecdf.png` | ECDF |
| 06 | `figures/06_qq.png` | QQ |
| 07–09 | ROC / PR / 혼동행렬 | 분류 평가(토이 로지스틱) |
| 10 | 스택 막대 | ETA구간×결과 |
| 11 | 에러바 | ETA별 가용률±std |
| 12 | 레이더 | 가용 vs 불가 프로필 |
| 13 | 워터폴(유사) | 샘플 축소 |
| 14 | 릿지(유사) | 구간별 밀도 |
| 15 | 패러럴 코디 | 다변수 궤적 |
| 16 | 트리맵(유사) | 구간×결과 면적 |
| 17 | 생키(유사) | 단수/복수→결과 |

## 주의

- **호기심·발표용 갤러리**이지, 새 MVP 피처/점수 확정이 아닙니다.
- ROC·PR·혼동행렬은 `available_count` 등 소수 피처 로지스틱 **베이스라인**입니다 (운영 모델 아님).
- 양성률이 높아 PR이 ROC보다 해석에 유리합니다.

```
DA① | chart-type gallery | {stamp}
```
""",
        encoding="utf-8",
    )
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    print("SHARE", share)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
