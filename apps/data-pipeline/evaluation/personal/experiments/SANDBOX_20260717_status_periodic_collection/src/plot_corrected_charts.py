"""Bias-corrected charts using forward-fill panel reconstruction.

Outputs:
  - chart_bias_comparison.png    : 3 ways to compute availability
  - chart_availability_panel.png : unbiased hourly availability
  - chart_day_comparison_panel.png : unbiased day comparison
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt

from build_panel import availability_timeseries, bias_summary, build_state_panel

SANDBOX_ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = SANDBOX_ROOT / "reports"


def _style() -> None:
    plt.rcParams["font.family"] = ["Malgun Gothic", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False


def plot_bias_comparison(summary: dict) -> Path:
    fig, ax = plt.subplots(figsize=(10, 5.5), facecolor="#f7f8fa")
    labels = [
        "관측행 평균\n(편향: 바쁜 충전기 과대)",
        "충전기 1표 평균\n(관측된 것만)",
        "패널 재구성\n(편향 제거, 권장)",
    ]
    vals = [
        summary["row_weighted_pct"],
        summary["charger_weighted_pct"],
        summary["panel_weighted_pct"],
    ]
    colors = ["#b24c63", "#e2b93b", "#18794e"]
    bars = ax.bar(labels, vals, color=colors, width=0.6)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.8, f"{v:.1f}%",
                ha="center", fontsize=13, fontweight="bold")
    ax.set_title("같은 데이터, 계산 방식에 따라 달라지는 가용률",
                 loc="left", fontweight="bold", fontsize=15)
    ax.set_ylabel("전체 충전 가용률 (%)")
    ax.set_ylim(0, 80)
    ax.grid(axis="y", alpha=0.25)
    ax.set_facecolor("#ffffff")
    ax.spines[["top", "right"]].set_visible(False)
    ax.annotate(
        f"같은 원본인데 {vals[0] - vals[1]:.1f}%p 차이 →\n"
        "집계 방식이 결과를 좌우",
        xy=(0, vals[0]), xytext=(0.35, 74),
        fontsize=10, color="#8a2d43",
        arrowprops={"arrowstyle": "->", "color": "#8a2d43"},
    )
    fig.text(0.06, 0.01,
             f"관측 1회뿐인 충전기 {summary['observed_once_pct']:.0f}% · "
             "Source: status snapshots · EXP-020",
             fontsize=8.5, color="#68737d")
    out = REPORT_DIR / "chart_bias_comparison.png"
    fig.savefig(out, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_hourly_panel(ts) -> Path:
    hourly = ts.groupby("hour")["availability_pct"].mean()
    fig, ax = plt.subplots(figsize=(11, 5), facecolor="#f7f8fa")
    bars = ax.bar(hourly.index, hourly.values, color="#18794e")
    overall = ts["availability_pct"].mean()
    ax.axhline(overall, color="#b24c63", linestyle="--", linewidth=1.5,
               label=f"전체 평균 {overall:.1f}%")
    for b, r in zip(bars, hourly.values):
        ax.text(b.get_x() + b.get_width() / 2, r + 0.6, f"{r:.0f}",
                ha="center", fontsize=8)
    ax.set_title("시간대별 충전 가용률 (패널 재구성 · 편향 제거)",
                 loc="left", fontweight="bold", fontsize=14)
    ax.set_xlabel("시각 (시, KST)")
    ax.set_ylabel("가용률 (%) · 충전기 1대=1표")
    ax.set_xticks(range(0, 24))
    ax.set_ylim(0, 100)
    ax.legend(loc="upper right")
    ax.grid(axis="y", alpha=0.25)
    ax.set_facecolor("#ffffff")
    ax.spines[["top", "right"]].set_visible(False)
    fig.text(0.06, 0.01,
             "정의: 각 시점 함대 상태를 forward-fill로 복원 후 가용률 · EXP-020",
             fontsize=8.5, color="#68737d")
    out = REPORT_DIR / "chart_availability_panel.png"
    fig.savefig(out, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_day_panel(ts) -> Path:
    fig, ax = plt.subplots(figsize=(12, 5), facecolor="#f7f8fa")
    palette = ["#4c78a8", "#5bb98c", "#d08c45", "#8a5cd1"]
    import pandas as pd

    for i, (date, part) in enumerate(ts.groupby("date")):
        rate = part.groupby("hour")["availability_pct"].mean()
        weekday = pd.Timestamp(date).day_name()
        ax.plot(rate.index, rate.values, marker="o", markersize=4,
                color=palette[i % len(palette)], linewidth=2,
                label=f"{date} ({weekday})")
    ax.set_title("일자별 시간대 가용률 (패널 재구성 · 편향 제거)",
                 loc="left", fontweight="bold", fontsize=14)
    ax.set_xlabel("시각 (시, KST)")
    ax.set_ylabel("가용률 (%) · 충전기 1대=1표")
    ax.set_xticks(range(0, 24))
    ax.set_ylim(0, 100)
    ax.legend()
    ax.grid(alpha=0.25)
    ax.set_facecolor("#ffffff")
    ax.spines[["top", "right"]].set_visible(False)
    fig.text(0.06, 0.01,
             "표본: 2일치 (요일 패턴은 누적 후 재평가) · EXP-020",
             fontsize=8.5, color="#68737d")
    out = REPORT_DIR / "chart_day_comparison_panel.png"
    fig.savefig(out, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return out


def main() -> int:
    _style()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    summary = bias_summary()
    panel = build_state_panel()
    ts = availability_timeseries(panel)
    outs = [
        plot_bias_comparison(summary),
        plot_hourly_panel(ts),
        plot_day_panel(ts),
    ]
    for o in outs:
        print(o)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
