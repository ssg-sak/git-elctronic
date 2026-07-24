"""Make teammate-friendly charts for TMAP ETA sample (DA①)."""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import font_manager

_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))
from _bootstrap import ensure_paths

REPO = ensure_paths()

# Korean labels
for fp in (Path(r"C:\Windows\Fonts\malgun.ttf"), Path(r"C:\Windows\Fonts\malgunbd.ttf")):
    if fp.is_file():
        font_manager.fontManager.addfont(str(fp))
plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

SAMPLE = REPO / "docs/data/analysis/tmap_eta_sample_20260723"
CSV = SAMPLE / "haversine_vs_tmap_eta.csv"
FIG = SAMPLE / "figures"
FIG.mkdir(parents=True, exist_ok=True)

# palette — avoid purple / cream AI clichés
C_HV = "#1F6B4A"  # forest
C_TM = "#C45C26"  # terracotta-orange but used sparingly as accent for TMAP
C_BG = "#F7F5F0"
C_GRID = "#D9D4C8"
C_INK = "#1A1A1A"
C_MUTED = "#5C5C5C"
C_KEEP = "#2E7D4F"
C_DROP = "#B33A3A"
C_REVIEW = "#B08900"


def _short_name(s: str, n: int = 12) -> str:
    s = str(s).replace(" ", "")
    return s if len(s) <= n else s[: n - 1] + "…"


def main() -> None:
    df = pd.read_csv(CSV)
    df["label"] = [
        f"{i}. {_short_name(nm)}" for i, nm in zip(df["rank_by_haversine"], df["statNm"])
    ]
    # rank 1 at top
    plot_df = df.iloc[::-1].reset_index(drop=True)
    y = np.arange(len(plot_df))

    # ── 1) Side-by-side ETA bars ──────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(11, 7.2), facecolor=C_BG)
    ax.set_facecolor(C_BG)
    h = 0.35
    ax.barh(
        y + h / 2,
        plot_df["haversine_eta_min_proxy"],
        height=h,
        color=C_HV,
        label="직선거리 환산(분) — 참고용",
    )
    ax.barh(
        y - h / 2,
        plot_df["tmap_eta_min"],
        height=h,
        color=C_TM,
        label="TMAP 실제 도로 ETA(분)",
    )
    ax.set_yticks(y)
    ax.set_yticklabels(plot_df["label"].tolist())
    ax.set_xlabel("분", color=C_INK)
    ax.set_title(
        "왜 직선거리만 쓰면 안 되나\n가까운 15곳: 직선 환산 vs TMAP 도로 이동시간",
        color=C_INK,
        pad=12,
    )
    ax.legend(loc="lower right", frameon=False)
    ax.grid(axis="x", color=C_GRID, linewidth=0.8)
    ax.spines[["top", "right"]].set_visible(False)
    # callout on 동대구복합환승센터 (rank 6 → in reversed plot)
    hit = plot_df.index[plot_df["statId"] == "CV003123"]
    if len(hit):
        yi = int(hit[0])
        ax.annotate(
            "예: 동대구복합환승센터\n직선~0.7분 → TMAP 9분",
            xy=(9.0, yi - h / 2),
            xytext=(10.2, yi + 1.5),
            fontsize=9,
            color=C_MUTED,
            arrowprops=dict(arrowstyle="->", color=C_MUTED),
        )
    fig.tight_layout()
    p1 = FIG / "01_직선환산_vs_TMAP_ETA.png"
    fig.savefig(p1, dpi=160, bbox_inches="tight", facecolor=C_BG)
    plt.close(fig)

    # ── 2) Rank flip: haversine km rank vs TMAP ETA rank ──────────────────
    df2 = df.copy()
    df2["rank_tmap"] = df2["tmap_eta_min"].rank(method="min").astype(int)
    fig, ax = plt.subplots(figsize=(8.5, 7), facecolor=C_BG)
    ax.set_facecolor(C_BG)
    for _, r in df2.iterrows():
        ax.plot(
            [1, 2],
            [r["rank_by_haversine"], r["rank_tmap"]],
            color=C_GRID,
            lw=1.6,
            zorder=1,
        )
        ax.scatter([1], [r["rank_by_haversine"]], s=60, color=C_HV, zorder=2)
        ax.scatter([2], [r["rank_tmap"]], s=60, color=C_TM, zorder=2)
        ax.text(0.92, r["rank_by_haversine"], _short_name(r["statNm"], 10), ha="right", va="center", fontsize=8, color=C_MUTED)
        ax.text(2.08, r["rank_tmap"], f"{r['tmap_eta_min']}분", ha="left", va="center", fontsize=8, color=C_INK)
    ax.set_xlim(0.5, 2.5)
    ax.set_ylim(len(df2) + 0.5, 0.5)
    ax.set_xticks([1, 2])
    ax.set_xticklabels(["직선거리 순위\n(가까움→)", "TMAP ETA 순위\n(빠름→)"], color=C_INK)
    ax.set_ylabel("순위 (1이 최상)", color=C_INK)
    ax.set_title("순위가 뒤바뀐다\n직선으로 1등이 TMAP에선 밀릴 수 있음", color=C_INK, pad=12)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color=C_GRID, lw=0.6)
    fig.tight_layout()
    p2 = FIG / "02_순위_뒤집힘.png"
    fig.savefig(p2, dpi=160, bbox_inches="tight", facecolor=C_BG)
    plt.close(fig)

    # ── 3) Distance vs road distance scatter ──────────────────────────────
    fig, ax = plt.subplots(figsize=(8, 6.2), facecolor=C_BG)
    ax.set_facecolor(C_BG)
    ax.scatter(df["haversine_km"], df["tmap_road_km"], s=70, color=C_TM, zorder=3)
    mx = max(df["haversine_km"].max(), df["tmap_road_km"].max()) * 1.15
    ax.plot([0, mx], [0, mx], ls="--", color=C_HV, lw=1.2, label="직선 = 도로 (이상)")
    for _, r in df.iterrows():
        if r["tmap_road_km"] / max(r["haversine_km"], 1e-6) > 8:
            ax.annotate(
                _short_name(r["statNm"], 14),
                (r["haversine_km"], r["tmap_road_km"]),
                textcoords="offset points",
                xytext=(6, 4),
                fontsize=8,
                color=C_MUTED,
            )
    ax.set_xlabel("직선거리 (km)", color=C_INK)
    ax.set_ylabel("TMAP 도로거리 (km)", color=C_INK)
    ax.set_title("직선 0.3km여도 도로로는 2km일 수 있다", color=C_INK, pad=12)
    ax.legend(frameon=False, loc="upper left")
    ax.grid(color=C_GRID, lw=0.7)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    p3 = FIG / "03_직선거리_vs_도로거리.png"
    fig.savefig(p3, dpi=160, bbox_inches="tight", facecolor=C_BG)
    plt.close(fig)

    # ── 4) Pipeline / who-does-what board ─────────────────────────────────
    fig, ax = plt.subplots(figsize=(11, 4.8), facecolor=C_BG)
    ax.set_facecolor(C_BG)
    ax.set_xlim(0, 11)
    ax.set_ylim(0, 5)
    ax.axis("off")
    ax.set_title("역할 한 장 요약 — 누가 뭘 하나", color=C_INK, pad=8, fontsize=14)

    boxes = [
        (0.3, 2.2, 2.4, 2.0, "① DA\n충전소·useTime\n적재/파서", C_HV),
        (3.0, 2.2, 2.4, 2.0, "② 백엔드\n후보 3~5곳만\nTMAP 호출", C_TM),
        (5.7, 2.2, 2.4, 2.0, "③ 백엔드\n도착시각×\nuseTime 필터", "#3D5A80"),
        (8.4, 2.2, 2.4, 2.0, "④ 추천/FE\n점수·화면\n표시", "#4A5568"),
    ]
    for x, y0, w, h0, text, col in boxes:
        ax.add_patch(
            plt.Rectangle((x, y0), w, h0, facecolor=col, edgecolor="none", alpha=0.92, zorder=2)
        )
        ax.text(x + w / 2, y0 + h0 / 2, text, ha="center", va="center", color="white", fontsize=11, fontweight="bold", zorder=3)
    for x in (2.75, 5.45, 8.15):
        ax.annotate("", xy=(x + 0.2, 3.2), xytext=(x - 0.15, 3.2), arrowprops=dict(arrowstyle="->", color=C_INK, lw=1.8))

    ax.text(
        5.5,
        0.9,
        "DA는 TMAP 루프를 돌리지 않음 · 이번 산출은 “왜 필요한지” 보여주는 15건 샘플뿐",
        ha="center",
        va="center",
        fontsize=10,
        color=C_MUTED,
    )
    ax.add_patch(plt.Rectangle((0.3, 0.35), 10.5, 1.15, fill=False, edgecolor=C_GRID, lw=1.2, ls="--"))
    fig.tight_layout()
    p4 = FIG / "04_역할_한장요약.png"
    fig.savefig(p4, dpi=160, bbox_inches="tight", facecolor=C_BG)
    plt.close(fig)

    # ── 5) Arrival gate strip (all KEEP today — still show legend) ────────
    fig, ax = plt.subplots(figsize=(10, 3.8), facecolor=C_BG)
    ax.set_facecolor(C_BG)
    colors = {"KEEP": C_KEEP, "DROP": C_DROP, "REVIEW": C_REVIEW}
    counts = df["da_arrival_gate"].value_counts()
    labels = ["KEEP\n도착 시 영업", "DROP\n도착 시 마감", "REVIEW\nUNKNOWN"]
    keys = ["KEEP", "DROP", "REVIEW"]
    vals = [int(counts.get(k, 0)) for k in keys]
    bars = ax.bar(labels, vals, color=[colors[k] for k in keys], width=0.55)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.15, str(v), ha="center", fontsize=14, fontweight="bold", color=C_INK)
    ax.set_ylim(0, max(vals) * 1.35 + 1)
    ax.set_ylabel("충전소 수 (샘플 15)", color=C_INK)
    ax.set_title("도착시각 × useTime 게이트 (샘플 시점 17:01 KST)", color=C_INK, pad=10)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color=C_GRID, lw=0.7)
    ax.text(
        0.5,
        -0.28,
        "오늘 샘플은 전부 KEEP · 야간·마감 직전엔 DROP이 생김 → 정렬 전에 반드시 거르기",
        transform=ax.transAxes,
        ha="center",
        fontsize=9,
        color=C_MUTED,
    )
    fig.tight_layout()
    p5 = FIG / "05_도착_useTime_게이트.png"
    fig.savefig(p5, dpi=160, bbox_inches="tight", facecolor=C_BG)
    plt.close(fig)

    print("wrote", p1.name, p2.name, p3.name, p4.name, p5.name)


if __name__ == "__main__":
    main()
