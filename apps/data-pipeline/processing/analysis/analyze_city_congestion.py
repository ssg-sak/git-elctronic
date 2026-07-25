"""City-wide congestion time series from loop3 linkspeed (no station join).

Usage (repo root):
  python apps/data-pipeline/processing/analysis/analyze_city_congestion.py

Reads: docs/data/loops/loop3/daegu_traffic_linkspeed_*.csv
Writes: docs/data/analysis/city_congestion_<stamp>/
        + docs/팀공유/도시혼잡_시계열_<stamp>/ (figures + easy README)
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import sys

_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))
from _bootstrap import ensure_paths

REPO = ensure_paths()
from loop_paths import loop3_dir

KST = ZoneInfo("Asia/Seoul")
LOOP3 = loop3_dir()

plt.rcParams["font.family"] = ["Malgun Gothic", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def _norm_grade(s: pd.Series) -> pd.Series:
    """Map API variants to 1=원활, 2=지체, 3=정체."""
    x = s.astype(str).str.strip()
    x = x.str.replace(r"^0+", "", regex=True)
    x = x.replace({"": pd.NA, "nan": pd.NA, "None": pd.NA})
    return pd.to_numeric(x, errors="coerce")


def load_tick_summaries() -> pd.DataFrame:
    from loop_paths import iter_loop3_csvs

    files = iter_loop3_csvs(LOOP3, kind="linkspeed")
    rows: list[dict] = []
    for path in files:
        sid = path.stem.replace("daegu_traffic_linkspeed_", "")
        try:
            ts = pd.to_datetime(sid, format="%Y%m%d_%H%M%S")
        except ValueError:
            continue
        df = pd.read_csv(path, low_memory=False)
        if df.empty:
            continue
        g = _norm_grade(df["congGrade"]) if "congGrade" in df.columns else pd.Series(dtype=float)
        n = int(len(df))
        n1 = int((g == 1).sum())
        n2 = int((g == 2).sum())
        n3 = int((g == 3).sum())
        known = n1 + n2 + n3
        speed = pd.to_numeric(df.get("speedKph"), errors="coerce")
        rows.append(
            {
                "ts": ts,
                "file": path.name,
                "links": n,
                "n_smooth": n1,
                "n_slow": n2,
                "n_jam": n3,
                "pct_smooth": round(100.0 * n1 / known, 2) if known else None,
                "pct_slow": round(100.0 * n2 / known, 2) if known else None,
                "pct_jam": round(100.0 * n3 / known, 2) if known else None,
                "pct_congested": round(100.0 * (n2 + n3) / known, 2) if known else None,
                "speed_mean": round(float(speed.mean()), 2) if speed.notna().any() else None,
                "speed_median": round(float(speed.median()), 2) if speed.notna().any() else None,
            }
        )
    out = pd.DataFrame(rows).sort_values("ts").reset_index(drop=True)
    if len(out):
        out["ts"] = pd.to_datetime(out["ts"])
        out["hour"] = out["ts"].dt.hour
        out["date"] = out["ts"].dt.date.astype(str)
    return out


def hourly_union(ticks: pd.DataFrame) -> pd.DataFrame:
    g = (
        ticks.groupby("hour", as_index=False)
        .agg(
            ticks=("ts", "size"),
            days=("date", "nunique"),
            pct_smooth_mean=("pct_smooth", "mean"),
            pct_slow_mean=("pct_slow", "mean"),
            pct_jam_mean=("pct_jam", "mean"),
            pct_congested_mean=("pct_congested", "mean"),
            speed_mean=("speed_mean", "mean"),
            speed_median_of_means=("speed_mean", "median"),
        )
        .set_index("hour")
        .reindex(range(24))
    )
    return g


def plot_timeseries(ticks: pd.DataFrame, fig_dir: Path) -> Path:
    fig, axes = plt.subplots(2, 1, figsize=(13, 7.2), sharex=True, facecolor="#f7f8fa")
    ax1, ax2 = axes
    for ax in axes:
        ax.set_facecolor("#ffffff")
        ax.grid(axis="y", alpha=0.25)
        ax.spines[["top", "right"]].set_visible(False)

    ax1.fill_between(ticks["ts"], ticks["pct_jam"], color="#c44e52", alpha=0.35, label="정체 %")
    ax1.plot(ticks["ts"], ticks["pct_congested"], color="#e45756", lw=1.8, label="지체+정체 %")
    ax1.plot(ticks["ts"], ticks["pct_smooth"], color="#18794e", lw=1.6, label="원활 %")
    ax1.set_ylabel("% of links")
    ax1.set_ylim(0, 100)
    ax1.set_title("대구 도시 혼잡 시계열 (loop3 linkspeed · 소별 조인 없음)", loc="left", fontweight="bold")
    ax1.legend(loc="upper right", frameon=False, ncol=3)

    ax2.plot(ticks["ts"], ticks["speed_mean"], color="#4c78a8", lw=1.8, label="평균 속도 km/h")
    ax2.set_ylabel("km/h")
    ax2.set_xlabel("시각 (KST)")
    ax2.legend(loc="upper right", frameon=False)
    ax2.text(
        0.01,
        -0.22,
        "분모=등급 있는 링크 수(~1960). 충전소 좌표 조인 없음 — 도시 전체 맥락용.",
        transform=ax2.transAxes,
        fontsize=9,
        color="#555",
    )
    out = fig_dir / "01_congestion_timeseries.png"
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_hourly_profile(hourly: pd.DataFrame, fig_dir: Path) -> Path:
    hours = np.arange(24)
    fig, ax1 = plt.subplots(figsize=(13, 4.8), facecolor="#f7f8fa")
    ax1.set_facecolor("#ffffff")

    jam = hourly["pct_jam_mean"].fillna(0).to_numpy()
    slow = hourly["pct_slow_mean"].fillna(0).to_numpy()
    smooth = hourly["pct_smooth_mean"].fillna(0).to_numpy()
    ax1.bar(hours, jam, width=0.7, color="#c44e52", label="정체 %")
    ax1.bar(hours, slow, width=0.7, bottom=jam, color="#f58518", label="지체 %")
    ax1.bar(hours, smooth, width=0.7, bottom=jam + slow, color="#54a24b", alpha=0.85, label="원활 %")
    ax1.set_xticks(hours)
    ax1.set_xlim(-0.5, 23.5)
    ax1.set_ylim(0, 100)
    ax1.set_ylabel("링크 비율 (%)")
    ax1.set_xlabel("시 (KST) — 모든 일자 합집합")
    ax1.set_title("시간대별 도시 혼잡 구성 (원활/지체/정체)", loc="left", fontweight="bold")
    ax1.grid(axis="y", alpha=0.25)
    ax1.spines[["top", "right"]].set_visible(False)

    ax2 = ax1.twinx()
    ax2.plot(
        hours,
        hourly["speed_mean"],
        color="#4c78a8",
        lw=2.2,
        marker="o",
        ms=4,
        label="평균 속도",
    )
    ax2.set_ylabel("평균 속도 (km/h)")
    ax2.spines[["top"]].set_visible(False)

    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, loc="upper right", frameon=False, ncol=2)
    ax1.text(
        0.01,
        -0.18,
        "해석: 출퇴근대에 지체+정체↑ · 심야에 원활↑ 이면 정상. 가용률 08/09와 나란히 보면 ‘출발 시각’ 힌트.",
        transform=ax1.transAxes,
        fontsize=9,
        color="#555",
    )
    out = fig_dir / "02_hourly_congestion_profile.png"
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_vs_availability(ticks: pd.DataFrame, fig_dir: Path) -> Path | None:
    """Optional overlay with charger availability hourly union if present."""
    avail_path = (
        REPO
        / "docs/data/analysis/snapshot_all_20260723/availability_by_hour_union.csv"
    )
    if not avail_path.exists() or ticks.empty:
        return None
    avail = pd.read_csv(avail_path)
    if "hour" not in avail.columns:
        return None
    hourly = hourly_union(ticks).reset_index()
    m = hourly.merge(avail, on="hour", how="inner", suffixes=("_cong", "_avail"))
    if m.empty:
        return None

    fig, ax1 = plt.subplots(figsize=(13, 4.8), facecolor="#f7f8fa")
    ax1.set_facecolor("#ffffff")
    ax1.plot(m["hour"], m["mean_pct"], color="#18794e", lw=2.2, marker="o", label="충전기 가용률 %")
    ax1.set_ylabel("가용률 (%)", color="#18794e")
    ax1.set_ylim(0, 100)
    ax1.set_xticks(range(24))
    ax1.set_xlim(-0.5, 23.5)
    ax1.grid(axis="y", alpha=0.25)
    ax1.spines[["top"]].set_visible(False)

    ax2 = ax1.twinx()
    ax2.plot(
        m["hour"],
        m["pct_congested_mean"],
        color="#e45756",
        lw=2.2,
        marker="s",
        label="지체+정체 %",
    )
    ax2.set_ylabel("혼잡(지체+정체) %", color="#e45756")
    ax2.set_ylim(0, 100)
    ax2.spines[["top"]].set_visible(False)

    ax1.set_title(
        "시간대: 충전기 가용률 vs 도시 혼잡 (합집합 · 참고용)",
        loc="left",
        fontweight="bold",
    )
    ax1.set_xlabel("시 (KST)")
    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, loc="lower right", frameon=False)
    ax1.text(
        0.01,
        -0.18,
        "같은 시각끼리만 비교. 인과 단정 금지 — ‘같이 보면 출발 창이 보인다’ 수준.",
        transform=ax1.transAxes,
        fontsize=9,
        color="#555",
    )
    out = fig_dir / "03_hourly_vs_availability.png"
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return out


def write_readme(share: Path, summary: dict) -> None:
    lines = [
        "# 도시 혼잡 시계열 (loop3)",
        "",
        "| | |",
        "|---|---|",
        f"| **생성** | {summary['generated_at']} |",
        f"| **틱** | {summary['ticks']} |",
        f"| **구간** | {summary['first_ts']} ~ {summary['last_ts']} |",
        "| **의미** | 대구 도로 링크(~1960)의 **원활/지체/정체** 비율 · 평균 속도 |",
        "| **안 하는 것** | 충전소별 조인 · ETA 대체 |",
        "",
        "## 그림",
        "",
        "| 파일 | 한 줄 |",
        "|---|---|",
        "| `figures/01_congestion_timeseries.png` | 틱별 원활·혼잡·속도 |",
        "| `figures/02_hourly_congestion_profile.png` | 0~23시 혼잡 구성 |",
        "| `figures/03_hourly_vs_availability.png` | (있으면) 가용률과 나란히 |",
        "",
        "## ②·BE에게",
        "",
        "- 피처 후보: 시간대 `pct_congested` / `speed_mean` (도시 맥락)",
        "- ETA 정본은 **TMAP**. 이건 보조·설명용.",
        "",
        "```",
        f"DA① | city congestion | {summary.get('stamp')}",
        "```",
        "",
    ]
    (share / "README.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    ticks = load_tick_summaries()
    if ticks.empty:
        raise SystemExit(f"no linkspeed ticks under {LOOP3}")

    stamp = datetime.now(KST).strftime("%Y%m%d")
    out = REPO / "docs" / "data" / "analysis" / f"city_congestion_{stamp}"
    fig_dir = out / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)

    hourly = hourly_union(ticks)
    ticks.to_csv(out / "congestion_timeseries.csv", index=False, encoding="utf-8-sig")
    hourly.round(2).to_csv(out / "congestion_by_hour_union.csv", encoding="utf-8-sig")

    figs = [
        plot_timeseries(ticks, fig_dir),
        plot_hourly_profile(hourly, fig_dir),
    ]
    overlay = plot_vs_availability(ticks, fig_dir)
    if overlay:
        figs.append(overlay)

    summary = {
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "stamp": stamp,
        "source": str(LOOP3.relative_to(REPO)).replace("\\", "/"),
        "ticks": int(len(ticks)),
        "first_ts": str(ticks["ts"].iloc[0]),
        "last_ts": str(ticks["ts"].iloc[-1]),
        "links_per_tick_median": int(ticks["links"].median()),
        "pct_congested_mean": round(float(ticks["pct_congested"].mean()), 2),
        "pct_jam_mean": round(float(ticks["pct_jam"].mean()), 2),
        "speed_mean_overall": round(float(ticks["speed_mean"].mean()), 2),
        "figures": [p.name for p in figs],
        "note": "city-wide only; no station spatial join",
    }
    (out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    share = REPO / "docs" / "팀공유" / f"도시혼잡_시계열_{stamp}"
    share_fig = share / "figures"
    share_fig.mkdir(parents=True, exist_ok=True)
    for p in figs:
        shutil.copy2(p, share_fig / p.name)
    shutil.copy2(out / "congestion_by_hour_union.csv", share / "congestion_by_hour_union.csv")
    shutil.copy2(out / "summary.json", share / "summary.json")
    write_readme(share, summary)

    # tip in 팀공유 README if present
    team_readme = REPO / "docs" / "팀공유" / "README.md"
    if team_readme.exists():
        text = team_readme.read_text(encoding="utf-8")
        marker = f"도시혼잡_시계열_{stamp}"
        if marker not in text:
            row = (
                f"| **[`도시혼잡_시계열_{stamp}/`](./도시혼잡_시계열_{stamp}/)** "
                f"| 대구 도로 혼잡 시간대 (linkspeed) | 전원 · BE·② |\n"
            )
            if "| **[`시간대_가용률_" in text:
                text = text.replace(
                    "| **[`시간대_가용률_",
                    row + "| **[`시간대_가용률_",
                    1,
                )
            else:
                text += "\n" + row
            team_readme.write_text(text, encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"OUT={out}")
    print(f"SHARE={share}")


if __name__ == "__main__":
    main()
