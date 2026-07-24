"""Advanced shareable charts: coverage map, reliability, day comparison, dashboard.

Read-only. Joins snapshots (dedup at read time) with charger info for coords.
Outputs standalone PNGs under reports/.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from build_panel import availability_timeseries, build_state_panel
from load_snapshots import load_all_snapshots

SANDBOX_ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = SANDBOX_ROOT / "reports"
REPO_ROOT = SANDBOX_ROOT.parents[5]

# Daegu bounding box (drop out-of-region coordinate outliers)
DAEGU = {"lat": (35.6, 36.05), "lng": (128.35, 128.85)}


def _style() -> None:
    plt.rcParams["font.family"] = ["Malgun Gothic", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False


def _load() -> pd.DataFrame:
    df = load_all_snapshots()
    df["collectedAt"] = pd.to_datetime(df["snapshotId"], format="%Y%m%d_%H%M%S")
    df["stat"] = pd.to_numeric(df["stat"], errors="coerce")
    df["hour"] = df["collectedAt"].dt.hour
    df["fetched"] = pd.to_datetime(df["fetchedAt"], errors="coerce")
    df["upd"] = pd.to_datetime(df["statUpdDt"], format="%Y%m%d%H%M%S", errors="coerce")
    df["age_min"] = (df["fetched"] - df["upd"]).dt.total_seconds() / 60
    return df


def _info() -> pd.DataFrame:
    root = REPO_ROOT / "docs/data/extracted"
    files = sorted(root.rglob("daegu_charger_info_*.csv"))
    f = files[-1]
    di = pd.read_csv(f, dtype={"statId": str, "chgerId": str})
    di["lat"] = pd.to_numeric(di["lat"], errors="coerce")
    di["lng"] = pd.to_numeric(di["lng"], errors="coerce")
    return di[["statId", "lat", "lng"]].dropna().drop_duplicates("statId")


def plot_coverage_map(df: pd.DataFrame, info: pd.DataFrame) -> Path:
    obs_stations = set(df["statId"].unique())
    info = info[
        info["lat"].between(*DAEGU["lat"]) & info["lng"].between(*DAEGU["lng"])
    ].copy()
    info["observed"] = info["statId"].isin(obs_stations)

    fig, ax = plt.subplots(figsize=(9, 9), facecolor="#f7f8fa")
    miss = info[~info["observed"]]
    seen = info[info["observed"]]
    ax.scatter(miss["lng"], miss["lat"], s=10, c="#c8d0d8", alpha=0.6,
               label=f"미관측 {len(miss):,}개소")
    ax.scatter(seen["lng"], seen["lat"], s=14, c="#18794e", alpha=0.7,
               label=f"관측됨 {len(seen):,}개소")
    ax.set_title("대구 충전소 관측 커버리지 (지도)", loc="left",
                 fontweight="bold", fontsize=15)
    ax.set_xlabel("경도 (lng)")
    ax.set_ylabel("위도 (lat)")
    ax.legend(loc="upper right")
    ax.set_aspect("equal", adjustable="datalim")
    ax.grid(alpha=0.2)
    ax.set_facecolor("#ffffff")
    pct = len(seen) / len(info) * 100 if len(info) else 0
    fig.text(0.06, 0.02,
             f"관측 {len(seen):,} / 좌표보유 {len(info):,}개소 ({pct:.1f}%) · "
             "Source: status snapshots × charger_info · EXP-020",
             fontsize=8.5, color="#68737d")
    out = REPORT_DIR / "chart_coverage_map.png"
    fig.savefig(out, dpi=170, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_reliability(df: pd.DataFrame) -> Path:
    age = df["age_min"].dropna()
    age = age[(age >= 0) & (age <= 24 * 60)]
    high = (age < 5).sum()
    normal = ((age >= 5) & (age < 15)).sum()
    check = (age >= 15).sum()
    total = high + normal + check

    fig, axes = plt.subplots(1, 2, figsize=(13, 5), facecolor="#f7f8fa")
    labels = ["높음\n(<5분)", "보통\n(5~15분)", "확인필요\n(15분+)"]
    vals = [high, normal, check]
    colors = ["#18794e", "#e2b93b", "#b24c63"]
    bars = axes[0].bar(labels, vals, color=colors)
    for b, v in zip(bars, vals):
        axes[0].text(b.get_x() + b.get_width() / 2, v, f"{v/total*100:.1f}%",
                     ha="center", va="bottom", fontsize=10, fontweight="bold")
    axes[0].set_title("상태정보 신뢰도 등급 분포", loc="left", fontweight="bold", fontsize=13)
    axes[0].set_ylabel("관측 건수 (건)")
    axes[0].grid(axis="y", alpha=0.25)
    axes[0].set_facecolor("#ffffff")
    axes[0].spines[["top", "right"]].set_visible(False)

    capped = age.clip(upper=60)
    axes[1].hist(capped, bins=30, color="#4c78a8", edgecolor="white")
    axes[1].axvline(5, color="#18794e", linestyle="--", linewidth=1.3)
    axes[1].axvline(15, color="#b24c63", linestyle="--", linewidth=1.3)
    axes[1].set_title("상태 갱신 후 경과시간 분포 (60분 이상 합산)",
                      loc="left", fontweight="bold", fontsize=13)
    axes[1].set_xlabel("경과시간 (분): fetchedAt − statUpdDt")
    axes[1].set_ylabel("관측 건수 (건)")
    axes[1].grid(axis="y", alpha=0.25)
    axes[1].set_facecolor("#ffffff")
    axes[1].spines[["top", "right"]].set_visible(False)

    fig.text(0.06, 0.01,
             "신뢰도 기준: 5분 이내 높음 / 5~15분 보통 / 15분+ 확인필요 · EXP-020",
             fontsize=8.5, color="#68737d")
    out = REPORT_DIR / "chart_reliability.png"
    fig.savefig(out, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_day_comparison(df: pd.DataFrame) -> Path:
    df = df.copy()
    df["date"] = df["collectedAt"].dt.date
    sub = df[df["stat"].isin([2, 3])]
    fig, ax = plt.subplots(figsize=(12, 5), facecolor="#f7f8fa")
    palette = ["#4c78a8", "#5bb98c", "#d08c45", "#8a5cd1"]
    for i, (date, part) in enumerate(sub.groupby("date")):
        rate = part.groupby("hour")["stat"].apply(lambda s: (s == 2).mean() * 100)
        weekday = pd.Timestamp(date).day_name()
        ax.plot(rate.index, rate.values, marker="o", markersize=4,
                color=palette[i % len(palette)], linewidth=2,
                label=f"{date} ({weekday})")
    ax.set_title("일자별 시간대 가용률 비교", loc="left", fontweight="bold", fontsize=14)
    ax.set_xlabel("시각 (시, KST)")
    ax.set_ylabel("가용률 (%)")
    ax.set_xticks(range(0, 24))
    ax.set_ylim(0, 100)
    ax.legend()
    ax.grid(alpha=0.25)
    ax.set_facecolor("#ffffff")
    ax.spines[["top", "right"]].set_visible(False)
    fig.text(0.06, 0.01,
             "표본: 2일치 (요일 패턴은 누적 후 재평가) · Source: status snapshots · EXP-020",
             fontsize=8.5, color="#68737d")
    out = REPORT_DIR / "chart_day_comparison.png"
    fig.savefig(out, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_dashboard(
    df: pd.DataFrame,
    info: pd.DataFrame,
    panel: pd.DataFrame,
    panel_ts: pd.DataFrame,
) -> Path:
    fig = plt.figure(figsize=(16, 9.5), facecolor="#f7f8fa")
    gs = fig.add_gridspec(2, 3, hspace=0.4, wspace=0.32,
                          height_ratios=[1, 1])
    fig.suptitle("EV SafeCharge | status 수집 종합 대시보드",
                 fontsize=19, fontweight="bold", x=0.055, ha="left")
    fig.text(0.055, 0.935,
             f"{df['collectedAt'].min():%Y-%m-%d %H:%M} ~ "
             f"{df['collectedAt'].max():%Y-%m-%d %H:%M} KST · "
             f"{df['snapshotId'].nunique()}회 · 중복 제거 + 공백 안전 패널 재구성",
             fontsize=10.5, color="#52606d")

    # (1) coverage growth
    ax1 = fig.add_subplot(gs[0, 0])
    ids = sorted(df["snapshotId"].unique())
    seen: set = set()
    xs, ys = [], []
    for sid in ids:
        part = df[df["snapshotId"] == sid]
        seen.update(map(tuple, part[["statId", "chgerId"]].itertuples(index=False, name=None)))
        xs.append(pd.to_datetime(sid, format="%Y%m%d_%H%M%S"))
        ys.append(len(seen))
    ax1.plot(xs, ys, color="#18794e", linewidth=2.2)
    ax1.fill_between(xs, ys, color="#b7dfca", alpha=0.5)
    ax1.set_title("누적 고유 충전기", loc="left", fontweight="bold")
    ax1.set_ylabel("대")
    ax1.tick_params(axis="x", labelrotation=20, labelsize=8)
    ax1.grid(axis="y", alpha=0.25); ax1.set_facecolor("#fff")
    ax1.spines[["top", "right"]].set_visible(False)

    # (2) hourly availability — equal charger weight from the reconstructed panel
    ax2 = fig.add_subplot(gs[0, 1])
    rate = panel_ts.groupby("hour")["availability_pct"].mean()
    overall = panel_ts["availability_pct"].mean()
    ax2.bar(rate.index, rate.values, color="#5bb98c")
    ax2.axhline(
        overall,
        color="#b24c63",
        linestyle="--",
        linewidth=1.3,
        label=f"평균 {overall:.1f}%",
    )
    ax2.set_title("시간대별 가용률 (패널)", loc="left", fontweight="bold")
    ax2.set_ylabel("% · 충전기 1대=1표"); ax2.set_xlabel("시")
    ax2.set_ylim(0, 100); ax2.grid(axis="y", alpha=0.25); ax2.set_facecolor("#fff")
    ax2.legend(fontsize=8)
    ax2.spines[["top", "right"]].set_visible(False)

    # (3) panel state mix — not raw observation-row mix
    ax3 = fig.add_subplot(gs[0, 2])
    rc = panel.stack().value_counts()
    vals = [int(rc.get(2, 0)), int(rc.get(3, 0)),
            int(rc.drop(labels=[2, 3], errors="ignore").sum())]
    ax3.pie(vals, labels=["충전대기", "충전중", "기타"],
            autopct=lambda p: f"{p:.0f}%", startangle=90,
            colors=["#5bb98c", "#4c78a8", "#89939e"],
            wedgeprops={"width": 0.42}, textprops={"fontsize": 9})
    ax3.set_title("패널 상태 구성", loc="left", fontweight="bold")

    # (4) coverage map
    ax4 = fig.add_subplot(gs[1, 0])
    obs = set(df["statId"].unique())
    im = info[info["lat"].between(*DAEGU["lat"]) & info["lng"].between(*DAEGU["lng"])].copy()
    im["observed"] = im["statId"].isin(obs)
    ax4.scatter(im[~im.observed]["lng"], im[~im.observed]["lat"], s=6, c="#c8d0d8", alpha=0.5)
    ax4.scatter(im[im.observed]["lng"], im[im.observed]["lat"], s=8, c="#18794e", alpha=0.7)
    ax4.set_title("관측 커버리지 지도", loc="left", fontweight="bold")
    ax4.set_xlabel("lng"); ax4.set_ylabel("lat")
    ax4.set_aspect("equal", adjustable="datalim")
    ax4.grid(alpha=0.2); ax4.set_facecolor("#fff")

    # (5) observation histogram
    ax5 = fig.add_subplot(gs[1, 1])
    o = df.groupby(["statId", "chgerId"]).size().clip(upper=15)
    ax5.hist(o, bins=np.arange(0.5, 16.5, 1), color="#8a5cd1", edgecolor="white")
    ax5.axvline(o.median(), color="#b24c63", linestyle="--", linewidth=1.3)
    ax5.set_title("충전기별 관측 횟수", loc="left", fontweight="bold")
    ax5.set_xlabel("회 (15+합산)"); ax5.set_ylabel("대")
    ax5.grid(axis="y", alpha=0.25); ax5.set_facecolor("#fff")
    ax5.spines[["top", "right"]].set_visible(False)

    # (6) reliability
    ax6 = fig.add_subplot(gs[1, 2])
    age = df["age_min"].dropna(); age = age[(age >= 0) & (age <= 24 * 60)]
    vals = [(age < 5).sum(), ((age >= 5) & (age < 15)).sum(), (age >= 15).sum()]
    tot = sum(vals)
    bars = ax6.bar(["높음", "보통", "확인필요"], vals,
                   color=["#18794e", "#e2b93b", "#b24c63"])
    for b, v in zip(bars, vals):
        ax6.text(b.get_x() + b.get_width() / 2, v, f"{v/tot*100:.0f}%",
                 ha="center", va="bottom", fontsize=9, fontweight="bold")
    ax6.set_title("신뢰도 등급", loc="left", fontweight="bold")
    ax6.set_ylabel("건"); ax6.grid(axis="y", alpha=0.25); ax6.set_facecolor("#fff")
    ax6.spines[["top", "right"]].set_visible(False)

    fig.text(0.055, 0.015,
             "Source: EvCharger periodic status snapshots × charger_info · "
             "원본 보존, 읽기 단계 dedup · 수집 공백 시 패널 초기화 · EXP-020",
             fontsize=9, color="#68737d")
    out = REPORT_DIR / "dashboard_status_collection.png"
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return out


def main() -> int:
    _style()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    df = _load()
    info = _info()
    panel = build_state_panel()
    panel_ts = availability_timeseries(panel)
    outs = [
        plot_coverage_map(df, info),
        plot_reliability(df),
        plot_day_comparison(df),
        plot_dashboard(df, info, panel, panel_ts),
    ]
    for o in outs:
        print(o)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
