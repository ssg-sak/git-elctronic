"""Generate a variety of shareable charts from the status collection.

Read-only analysis via load_snapshots (dedup at read time).
Outputs several standalone PNGs under reports/.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from load_snapshots import load_all_snapshots

SANDBOX_ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = SANDBOX_ROOT / "reports"


def _style() -> None:
    plt.rcParams["font.family"] = ["Malgun Gothic", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False


def _prep() -> pd.DataFrame:
    df = load_all_snapshots()
    df["collectedAt"] = pd.to_datetime(df["snapshotId"], format="%Y%m%d_%H%M%S")
    df["stat"] = pd.to_numeric(df["stat"], errors="coerce")
    df["hour"] = df["collectedAt"].dt.hour
    return df


def plot_hourly_availability(df: pd.DataFrame) -> Path:
    sub = df[df["stat"].isin([2, 3])].copy()
    grp = sub.groupby("hour")["stat"].agg(
        avail=lambda s: (s == 2).sum(), total="count"
    )
    grp["rate"] = grp["avail"] / grp["total"] * 100
    fig, ax = plt.subplots(figsize=(11, 5), facecolor="#f7f8fa")
    bars = ax.bar(grp.index, grp["rate"], color="#5bb98c")
    overall = sub["stat"].eq(2).mean() * 100
    ax.axhline(overall, color="#b24c63", linestyle="--", linewidth=1.5,
               label=f"전체 평균 {overall:.1f}%")
    for b, r in zip(bars, grp["rate"]):
        ax.text(b.get_x() + b.get_width() / 2, r + 0.6, f"{r:.0f}",
                ha="center", fontsize=8)
    ax.set_title("시간대별 충전 가용률 (충전대기 / (충전대기+충전중))",
                 loc="left", fontweight="bold", fontsize=14)
    ax.set_xlabel("시각 (시, KST)")
    ax.set_ylabel("가용률 (%)")
    ax.set_xticks(range(0, 24))
    ax.set_ylim(0, 100)
    ax.legend(loc="lower right")
    ax.grid(axis="y", alpha=0.25)
    ax.set_facecolor("#ffffff")
    ax.spines[["top", "right"]].set_visible(False)
    fig.text(0.06, 0.01, "Source: EvCharger periodic status snapshots · EXP-020",
             fontsize=8.5, color="#68737d")
    out = REPORT_DIR / "chart_hourly_availability.png"
    fig.savefig(out, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_collection_volume(df: pd.DataFrame) -> Path:
    per = df.groupby("collectedAt").size().reset_index(name="rows")
    fig, ax = plt.subplots(figsize=(12, 5), facecolor="#f7f8fa")
    ax.plot(per["collectedAt"], per["rows"], color="#4c78a8", linewidth=1.8,
            marker="o", markersize=3)
    # highlight the overnight gap
    gaps = per["collectedAt"].diff()
    gap_idx = gaps[gaps > pd.Timedelta(minutes=40)].index
    for gi in gap_idx:
        start = per["collectedAt"].iloc[gi - 1]
        end = per["collectedAt"].iloc[gi]
        ax.axvspan(start, end, color="#e2b93b", alpha=0.25)
        mid = start + (end - start) / 2
        ax.text(mid, per["rows"].max() * 0.9, "수집 공백\n(PC 종료)",
                ha="center", fontsize=9, color="#8a6d1a")
    ax.set_title("회차별 수집량 추이 (한 번에 받은 상태 변경 건수)",
                 loc="left", fontweight="bold", fontsize=14)
    ax.set_xlabel("수집 시각 (KST)")
    ax.set_ylabel("한 회차 관측 건수 (건)")
    ax.grid(axis="y", alpha=0.25)
    ax.set_facecolor("#ffffff")
    ax.spines[["top", "right"]].set_visible(False)
    fig.text(0.06, 0.01, "Source: EvCharger periodic status snapshots · EXP-020",
             fontsize=8.5, color="#68737d")
    out = REPORT_DIR / "chart_collection_volume.png"
    fig.savefig(out, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_observation_histogram(df: pd.DataFrame) -> Path:
    obs = df.groupby(["statId", "chgerId"]).size()
    capped = obs.clip(upper=15)
    fig, ax = plt.subplots(figsize=(11, 5), facecolor="#f7f8fa")
    bins = np.arange(0.5, 16.5, 1)
    ax.hist(capped, bins=bins, color="#8a5cd1", edgecolor="white")
    ax.axvline(obs.median(), color="#b24c63", linestyle="--", linewidth=1.5,
               label=f"중앙값 {obs.median():.0f}회")
    ax.axvline(obs.mean(), color="#18794e", linestyle="--", linewidth=1.5,
               label=f"평균 {obs.mean():.1f}회")
    ax.set_title("충전기별 관측 횟수 분포 (15회 이상은 15로 합산)",
                 loc="left", fontweight="bold", fontsize=14)
    ax.set_xlabel("관측 횟수 (회)")
    ax.set_ylabel("충전기 수 (대)")
    ax.set_xticks(range(1, 16))
    ax.set_xticklabels([str(i) for i in range(1, 15)] + ["15+"])
    ax.legend()
    ax.grid(axis="y", alpha=0.25)
    ax.set_facecolor("#ffffff")
    ax.spines[["top", "right"]].set_visible(False)
    fig.text(0.06, 0.01,
             f"Source: {len(obs):,} unique chargers · EXP-020",
             fontsize=8.5, color="#68737d")
    out = REPORT_DIR / "chart_observation_histogram.png"
    fig.savefig(out, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_status_by_hour(df: pd.DataFrame) -> Path:
    piv = (
        df[df["stat"].isin([2, 3])]
        .assign(name=lambda d: d["stat"].map({2: "충전대기", 3: "충전중"}))
        .groupby(["hour", "name"]).size().unstack(fill_value=0)
    )
    fig, ax = plt.subplots(figsize=(11, 5), facecolor="#f7f8fa")
    ax.bar(piv.index, piv.get("충전대기", 0), label="충전대기", color="#5bb98c")
    ax.bar(piv.index, piv.get("충전중", 0), bottom=piv.get("충전대기", 0),
           label="충전중", color="#4c78a8")
    ax.set_title("시간대별 관측 건수 (충전대기 vs 충전중)",
                 loc="left", fontweight="bold", fontsize=14)
    ax.set_xlabel("시각 (시, KST)")
    ax.set_ylabel("관측 건수 (건)")
    ax.set_xticks(range(0, 24))
    ax.legend()
    ax.grid(axis="y", alpha=0.25)
    ax.set_facecolor("#ffffff")
    ax.spines[["top", "right"]].set_visible(False)
    fig.text(0.06, 0.01, "Source: EvCharger periodic status snapshots · EXP-020",
             fontsize=8.5, color="#68737d")
    out = REPORT_DIR / "chart_status_by_hour.png"
    fig.savefig(out, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return out


def main() -> int:
    _style()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    df = _prep()
    outs = [
        plot_hourly_availability(df),
        plot_collection_volume(df),
        plot_observation_histogram(df),
        plot_status_by_hour(df),
    ]
    for o in outs:
        print(o)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
