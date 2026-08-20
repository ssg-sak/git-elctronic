"""UTIC incident (돌발) report from already-collected loop2 CSVs.

NOT a server loop — offline analysis of PC-collected ticks (through ~2026-07-22).

Usage (repo root):
  python apps/data-pipeline/processing/analysis/analyze_utic_incidents.py
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
KST = ZoneInfo("Asia/Seoul")
LOOP2 = REPO / "docs" / "data" / "loops" / "loop2"
JOIN = REPO / "docs" / "data" / "spatial_join" / "join_traffic_incident_utic_1000m.csv"

plt.rcParams["font.family"] = ["Malgun Gothic", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

# UTIC incidenteTypeCd — titles in our feed: 2≈공사 dominant
TYPE_NM = {1: "사고·기타(1)", 2: "공사·작업(2)", 5: "기타(5)"}


def load_ticks() -> tuple[pd.DataFrame, pd.DataFrame]:
    files = sorted(
        p
        for p in LOOP2.glob("daegu_traffic_incident_utic_*.csv")
        if "latest" not in p.name
    )
    frames = []
    tick_rows = []
    for path in files:
        sid = path.stem.replace("daegu_traffic_incident_utic_", "")
        try:
            ts = pd.to_datetime(sid, format="%Y%m%d_%H%M%S")
        except ValueError:
            continue
        df = pd.read_csv(path)
        df["_tick"] = sid
        df["_ts"] = ts
        frames.append(df)
        tick_rows.append(
            {
                "ts": ts,
                "n": len(df),
                "n_unique": df["incidentId"].nunique() if "incidentId" in df.columns else len(df),
                "file": path.name,
            }
        )
    all_df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    ticks = pd.DataFrame(tick_rows).sort_values("ts")
    return all_df, ticks


def unique_events(all_df: pd.DataFrame) -> pd.DataFrame:
    if all_df.empty:
        return all_df
    # last seen row per incidentId
    u = (
        all_df.sort_values("_ts")
        .groupby("incidentId", as_index=False)
        .tail(1)
        .copy()
    )
    u["type_nm"] = (
        pd.to_numeric(u.get("incidenteTypeCd"), errors="coerce")
        .map(TYPE_NM)
        .fillna("미상")
    )
    return u


def plot_tick_counts(ticks: pd.DataFrame, fig_dir: Path) -> Path:
    fig, ax = plt.subplots(figsize=(12, 4.2), facecolor="#f7f8fa")
    ax.set_facecolor("#ffffff")
    ax.plot(ticks["ts"], ticks["n"], color="#b279a2", lw=1.8, marker="o", ms=3)
    ax.fill_between(ticks["ts"], ticks["n"], alpha=0.2, color="#b279a2")
    ax.set_ylabel("대구 필터 돌발 건수")
    ax.set_xlabel("수집 시각 (KST)")
    ax.set_title("UTIC 돌발 틱별 건수 (이미 모은 CSV · 서버 루프 아님)", loc="left", fontweight="bold")
    ax.grid(axis="y", alpha=0.25)
    ax.spines[["top", "right"]].set_visible(False)
    ax.text(
        0.01,
        -0.2,
        "loop2 PC 수집분. Lightsail에는 UTIC 서비스 없음 · dgincident는 최근 0건.",
        transform=ax.transAxes,
        fontsize=9,
        color="#555",
    )
    out = fig_dir / "01_incident_count_by_tick.png"
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_type_and_roads(uniq: pd.DataFrame, fig_dir: Path) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6), facecolor="#f7f8fa")
    for ax in axes:
        ax.set_facecolor("#ffffff")
        ax.spines[["top", "right"]].set_visible(False)

    tc = uniq["type_nm"].value_counts()
    axes[0].bar(tc.index.astype(str), tc.values, color=["#f58518", "#4c78a8", "#54a24b"][: len(tc)])
    axes[0].set_title("고유 돌발 · 유형", loc="left", fontweight="bold")
    axes[0].tick_params(axis="x", rotation=15)
    for i, v in enumerate(tc.values):
        axes[0].text(i, v + 0.3, str(v), ha="center")

    roads = uniq["roadName"].fillna("(도로명없음)").astype(str).value_counts().head(8)
    axes[1].barh(roads.index[::-1], roads.values[::-1], color="#72b7b2")
    axes[1].set_title("고유 돌발 · 도로 Top8", loc="left", fontweight="bold")
    axes[1].set_xlabel("건수")

    out = fig_dir / "02_type_and_roads.png"
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_join_coverage(fig_dir: Path) -> tuple[Path, dict]:
    meta = {"join_exists": False}
    if not JOIN.exists():
        return fig_dir / "03_station_join_coverage.png", meta
    j = pd.read_csv(JOIN)
    matched = j["distance_m"].notna() if "distance_m" in j.columns else j.get("matched", False)
    if not isinstance(matched, pd.Series):
        matched = pd.Series([False] * len(j))
    else:
        # matched col may be string
        if matched.dtype == object:
            matched = matched.astype(str).str.lower().isin(["true", "1", "yes"]) | j["distance_m"].notna()
    n_hit = int(matched.sum())
    n_miss = len(j) - n_hit
    meta = {
        "join_exists": True,
        "stations": len(j),
        "matched": n_hit,
        "match_rate": round(n_hit / len(j), 4) if len(j) else 0,
        "radius_m": int(pd.to_numeric(j.get("radius_m"), errors="coerce").dropna().iloc[0])
        if "radius_m" in j.columns and j["radius_m"].notna().any()
        else 1000,
    }

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6), facecolor="#f7f8fa")
    for ax in axes:
        ax.set_facecolor("#ffffff")
        ax.spines[["top", "right"]].set_visible(False)

    axes[0].bar(["1km 내 돌발 있음", "없음"], [n_hit, n_miss], color=["#b279a2", "#d0d0d0"])
    axes[0].set_title(f"충전소×UTIC 돌발 조인 ({meta['radius_m']}m)", loc="left", fontweight="bold")
    axes[0].text(0, n_hit + 40, f"{n_hit}\n({100*n_hit/len(j):.1f}%)", ha="center")

    dist = pd.to_numeric(j.loc[matched, "distance_m"], errors="coerce").dropna()
    if len(dist):
        axes[1].hist(dist, bins=20, color="#b279a2", edgecolor="white")
        axes[1].axvline(dist.median(), color="#222", ls="--", label=f"중앙값 {dist.median():.0f}m")
        axes[1].legend(frameon=False)
    axes[1].set_title("매칭된 소 · 최근접 돌발 거리", loc="left", fontweight="bold")
    axes[1].set_xlabel("m")

    out = fig_dir / "03_station_join_coverage.png"
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return out, meta


def plot_map(uniq: pd.DataFrame, fig_dir: Path) -> Path | None:
    x = pd.to_numeric(uniq.get("locationDataX"), errors="coerce")
    y = pd.to_numeric(uniq.get("locationDataY"), errors="coerce")
    ok = x.notna() & y.notna()
    if ok.sum() < 3:
        return None
    fig, ax = plt.subplots(figsize=(7.5, 7.2), facecolor="#f7f8fa")
    ax.set_facecolor("#ffffff")
    types = uniq.loc[ok, "type_nm"]
    for nm, color in [("공사·작업(2)", "#f58518"), ("사고·기타(1)", "#e45756"), ("기타(5)", "#4c78a8")]:
        m = ok & (uniq["type_nm"] == nm)
        if m.any():
            ax.scatter(x[m], y[m], s=40, alpha=0.75, c=color, label=nm, edgecolors="white", linewidths=0.4)
    # leftover
    other = ok & ~uniq["type_nm"].isin(["공사·작업(2)", "사고·기타(1)", "기타(5)"])
    if other.any():
        ax.scatter(x[other], y[other], s=40, alpha=0.6, c="#9e9e9e", label="미상")
    ax.set_xlabel("경도")
    ax.set_ylabel("위도")
    ax.set_title("대구 UTIC 돌발 위치 (고유 사건)", loc="left", fontweight="bold")
    ax.legend(frameon=False, fontsize=9)
    ax.grid(alpha=0.2)
    ax.spines[["top", "right"]].set_visible(False)
    out = fig_dir / "04_incident_map.png"
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return out


def write_readme(out: Path, summary: dict, figs: list[Path]) -> None:
    lines = [
        "# UTIC 돌발 분석 (모아둔 것만 · 서버 루프 아님)",
        "",
        "| | |",
        "|---|---|",
        f"| **생성** | {summary['generated_at']} |",
        f"| **원천** | `docs/data/loops/loop2` UTIC CSV |",
        f"| **구간** | {summary['first_ts']} ~ {summary['last_ts']} |",
        f"| **틱** | {summary['ticks']} |",
        f"| **고유 돌발** | {summary['unique_incidents']} |",
        "| **서버** | Lightsail에 UTIC **안 올림** · 이 리포트는 오프라인 |",
        "",
        "## 한 줄",
        "",
        "> 7/21~7/22에 PC로 받아 둔 UTIC 대구 돌발을 다시 본 것. ",
        "> **실시간 서버 수집이 아님.** dgincident(대구)는 지금 0건이라 이번 그림은 UTIC 이력 중심.",
        "",
        "## 숫자",
        "",
        f"- 틱당 대구 건수: 대략 **{summary.get('n_per_tick_median')}** (median)",
        f"- 유형: `{summary.get('type_counts')}`",
        f"- 충전소 1km 조인: **{summary.get('join_matched')}** / {summary.get('join_stations')} "
        f"(rate={summary.get('join_match_rate')})",
        "",
        "## 그림",
        "",
    ]
    caps = {
        "01_incident_count_by_tick.png": "틱별 돌발 건수",
        "02_type_and_roads.png": "유형·도로 Top",
        "03_station_join_coverage.png": "충전소 1km 조인",
        "04_incident_map.png": "좌표 산점도",
    }
    for p in figs:
        lines += [f"### {p.name}", "", f"![{caps.get(p.name,p.name)}](figures/{p.name})", "", f"**{caps.get(p.name,p.name)}**", ""]

    lines += [
        "## 분석으로 쓸 만함 / 아님",
        "",
        "| | |",
        "|---|---|",
        "| ✅ | 소 근처 경고 (`nearest_incident_m`) · 공사 많은 도로 파악 |",
        "| ❌ | 단독 시계열 ML (건수 적음) · 지금 서버에 UTIC 올리기 |",
        "",
        "## 재실행",
        "",
        "```bash",
        "python apps/data-pipeline/processing/analysis/analyze_utic_incidents.py",
        "```",
        "",
        "```",
        f"DA① | UTIC incident offline report | {summary.get('stamp')}",
        "```",
        "",
    ]
    (out / "README.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    all_df, ticks = load_ticks()
    if all_df.empty:
        raise SystemExit(f"no UTIC CSVs under {LOOP2}")

    stamp = datetime.now(KST).strftime("%Y%m%d")
    out = REPO / "docs" / "팀공유" / f"돌발_UTIC_분석_{stamp}"
    fig_dir = out / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)

    uniq = unique_events(all_df)
    figs: list[Path] = [
        plot_tick_counts(ticks, fig_dir),
        plot_type_and_roads(uniq, fig_dir),
    ]
    p3, join_meta = plot_join_coverage(fig_dir)
    figs.append(p3)
    p4 = plot_map(uniq, fig_dir)
    if p4:
        figs.append(p4)

    type_counts = uniq["type_nm"].value_counts().to_dict()
    summary = {
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "stamp": stamp,
        "source": "docs/data/loops/loop2 (UTIC PC collect)",
        "server_loop": False,
        "ticks": int(len(ticks)),
        "first_ts": str(ticks["ts"].iloc[0]),
        "last_ts": str(ticks["ts"].iloc[-1]),
        "row_obs": int(len(all_df)),
        "unique_incidents": int(uniq["incidentId"].nunique()),
        "n_per_tick_median": int(ticks["n"].median()),
        "type_counts": type_counts,
        "join_stations": join_meta.get("stations"),
        "join_matched": join_meta.get("matched"),
        "join_match_rate": join_meta.get("match_rate"),
        "figures": [p.name for p in figs],
    }
    uniq_out = uniq.drop(columns=[c for c in uniq.columns if c.startswith("_")], errors="ignore")
    uniq_out.to_csv(out / "unique_incidents.csv", index=False, encoding="utf-8-sig")
    ticks.to_csv(out / "ticks_summary.csv", index=False, encoding="utf-8-sig")
    (out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_readme(out, summary, figs)

    analysis = REPO / "docs" / "data" / "analysis" / f"utic_incidents_{stamp}"
    if analysis.exists():
        shutil.rmtree(analysis)
    shutil.copytree(out, analysis)

    desk = Path.home() / "Desktop" / f"EV_SafeCharge_돌발_UTIC_분석_{stamp}"
    if desk.exists():
        shutil.rmtree(desk)
    shutil.copytree(out, desk)

    team = REPO / "docs" / "팀공유" / "README.md"
    if team.exists():
        text = team.read_text(encoding="utf-8")
        marker = f"돌발_UTIC_분석_{stamp}"
        if marker not in text:
            row = (
                f"| **[`돌발_UTIC_분석_{stamp}/`](./돌발_UTIC_분석_{stamp}/)** "
                f"| UTIC 돌발 이력 그림 (서버 루프 아님) | 전원 |\n"
            )
            if "| **[`D1_최신화의미_" in text:
                text = text.replace("| **[`D1_최신화의미_", row + "| **[`D1_최신화의미_", 1)
            else:
                text += "\n" + row
            team.write_text(text, encoding="utf-8")

    # tip in 운영 doc
    tip = REPO / "docs" / "data" / "운영" / "Lightsail_pull_및_돌발현황.md"
    if tip.exists():
        t = tip.read_text(encoding="utf-8")
        if "돌발_UTIC_분석_" not in t:
            t += (
                "\n\n## 5. 오프라인 분석 산출\n\n"
                f"- 팀공유: [`../../팀공유/돌발_UTIC_분석_{stamp}/`](../../팀공유/돌발_UTIC_분석_{stamp}/)\n"
                "- 재실행: `python apps/data-pipeline/processing/analysis/analyze_utic_incidents.py`\n"
            )
            tip.write_text(t, encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("DESKTOP", desk)


if __name__ == "__main__":
    main()
