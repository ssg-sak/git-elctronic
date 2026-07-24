"""Create a shareable visual summary of periodic status data value."""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from load_snapshots import load_all_snapshots

SANDBOX_ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = SANDBOX_ROOT / "reports"
OUT_PATH = REPORT_DIR / "status_data_value_20260718.png"
REPO_ROOT = SANDBOX_ROOT.parents[5]

def _total_chargers() -> int:
    files = sorted((REPO_ROOT / "docs/data/extracted").rglob("daegu_charger_info_*.csv"))
    if not files:
        raise FileNotFoundError("daegu_charger_info CSV not found")
    info = pd.read_csv(files[-1], dtype={"statId": str, "chgerId": str})
    return int(info.groupby(["statId", "chgerId"]).ngroups)


def main() -> int:
    df = load_all_snapshots()
    if df.empty:
        print("No snapshots found", file=sys.stderr)
        return 1

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    plt.rcParams["font.family"] = ["Malgun Gothic", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    df["collectedAt"] = pd.to_datetime(df["snapshotId"], format="%Y%m%d_%H%M%S")
    df["stat"] = pd.to_numeric(df["stat"], errors="coerce")
    snapshot_ids = sorted(df["snapshotId"].unique())

    seen: set[tuple[str, str]] = set()
    growth = []
    for sid in snapshot_ids:
        part = df[df["snapshotId"] == sid]
        seen.update(
            map(tuple, part[["statId", "chgerId"]].itertuples(index=False, name=None))
        )
        growth.append(
            {
                "time": pd.to_datetime(sid, format="%Y%m%d_%H%M%S"),
                "chargers": len(seen),
            }
        )
    growth_df = pd.DataFrame(growth)

    observations = df.groupby(["statId", "chgerId"]).size()
    repeat_levels = [2, 3, 5, 10]
    repeat_counts = [int((observations >= level).sum()) for level in repeat_levels]

    raw_status_counts = df["stat"].value_counts().sort_index()
    status_counts = pd.Series(
        {
            "충전대기": int(raw_status_counts.get(2, 0)),
            "충전중": int(raw_status_counts.get(3, 0)),
            "기타 상태": int(
                raw_status_counts.drop(labels=[2, 3], errors="ignore").sum()
            ),
        }
    )

    state_sets = df.groupby(["statId", "chgerId"])["stat"].agg(lambda values: set(values))
    both = int(state_sets.apply(lambda values: 2 in values and 3 in values).sum())
    total_info = _total_chargers()
    unique = int(len(observations))
    coverage = unique / total_info * 100
    span_hours = (
        growth_df["time"].max() - growth_df["time"].min()
    ).total_seconds() / 3600

    fig = plt.figure(figsize=(14, 8), facecolor="#f7f8fa")
    grid = fig.add_gridspec(2, 3, height_ratios=[1.35, 1], hspace=0.42, wspace=0.3)
    ax_growth = fig.add_subplot(grid[0, :2])
    ax_repeat = fig.add_subplot(grid[0, 2])
    ax_status = fig.add_subplot(grid[1, 0])
    ax_summary = fig.add_subplot(grid[1, 1:])

    fig.suptitle(
        "EV SafeCharge | 충전기 상태 수집 데이터 가치 평가",
        fontsize=18,
        fontweight="bold",
        x=0.06,
        ha="left",
    )
    fig.text(
        0.06,
        0.92,
        f"{growth_df['time'].min():%Y-%m-%d %H:%M} ~ "
        f"{growth_df['time'].max():%Y-%m-%d %H:%M} KST · "
        f"{len(snapshot_ids)}회 수집 · 중복 제거 후",
        fontsize=10,
        color="#52606d",
    )

    ax_growth.plot(
        growth_df["time"],
        growth_df["chargers"],
        color="#18794e",
        linewidth=2.5,
    )
    ax_growth.fill_between(
        growth_df["time"],
        growth_df["chargers"],
        color="#b7dfca",
        alpha=0.55,
    )
    ax_growth.scatter(
        growth_df["time"].iloc[-1],
        growth_df["chargers"].iloc[-1],
        color="#18794e",
        s=45,
        zorder=3,
    )
    ax_growth.annotate(
        f"{unique:,}대 ({coverage:.1f}%)",
        (growth_df["time"].iloc[-1], growth_df["chargers"].iloc[-1]),
        xytext=(-105, 15),
        textcoords="offset points",
        fontsize=10,
        fontweight="bold",
    )
    ax_growth.set_title("누적 고유 충전기 성장", loc="left", fontweight="bold")
    ax_growth.set_xlabel("수집 시각 (KST)")
    ax_growth.set_ylabel("누적 고유 충전기 (대)")
    ax_growth.grid(axis="y", alpha=0.25)

    ax_repeat.barh(
        [f"{level}회 이상" for level in repeat_levels],
        repeat_counts,
        color="#4c78a8",
    )
    for index, value in enumerate(repeat_counts):
        ax_repeat.text(value, index, f" {value:,}", va="center", fontsize=9)
    ax_repeat.invert_yaxis()
    ax_repeat.set_title("반복 관측 깊이", loc="left", fontweight="bold")
    ax_repeat.set_xlabel("충전기 수 (대)")
    ax_repeat.set_ylabel("최소 관측 횟수")
    ax_repeat.grid(axis="x", alpha=0.25)

    colors = ["#5bb98c", "#4c78a8", "#89939e"]
    ax_status.pie(
        status_counts.values,
        labels=status_counts.index,
        autopct=lambda pct: f"{pct:.1f}%" if pct >= 2 else "",
        startangle=90,
        colors=colors,
        textprops={"fontsize": 8},
    )
    ax_status.set_title("전체 관측행 상태 구성", loc="left", fontweight="bold")

    ax_summary.axis("off")
    ax_summary.set_title("현재 판단", loc="left", fontweight="bold")
    summary = (
        f"가치 있음\n\n"
        f"• {span_hours:.1f}시간 만에 대구 전체 {total_info:,}대 중 "
        f"{unique:,}대({coverage:.1f}%) 관측\n"
        f"• 충전대기·충전중을 모두 본 충전기 {both:,}대 "
        f"({both / unique * 100:.1f}%)\n"
        f"• 충전기당 관측 중앙값 {observations.median():.0f}회, "
        f"평균 {observations.mean():.1f}회\n\n"
        f"해석\n"
        f"반복 수집으로 관측 범위와 실제 상태 변화 신호가 쌓이고 있다.\n"
        f"다만 기간과 반복 깊이가 부족하므로 지금은 학습이 아니라 수집 단계다.\n"
        f"4주 이상 누적 후 같은 지표로 학습 진입 여부를 다시 판단한다."
    )
    ax_summary.text(
        0,
        0.93,
        summary,
        va="top",
        fontsize=11,
        linespacing=1.6,
        bbox={"boxstyle": "round,pad=0.8", "facecolor": "#ffffff", "edgecolor": "#c8d0d8"},
    )

    for axis in [ax_growth, ax_repeat]:
        axis.set_facecolor("#ffffff")
        axis.spines[["top", "right"]].set_visible(False)

    fig.text(
        0.06,
        0.02,
        "Source: EvCharger periodic status snapshots · EXP-020 · "
        "원본 보존, (snapshotId, statId, chgerId) 기준 읽기 단계 dedup",
        fontsize=8.5,
        color="#68737d",
    )
    fig.savefig(OUT_PATH, dpi=180, bbox_inches="tight")
    plt.close(fig)
    print(OUT_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
