"""Charts + reliability checks over the full status snapshot corpus.

Reads/rebuilds the same unique snapshot union as analyze_all_snapshots.py.
Writes PNGs + reliability tables under docs/data/analysis/snapshot_all_20260723/
and docs/보고/스냅샷_시각_신뢰도_20260723.md
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

SRC = Path(__file__).resolve().parent
REPO = Path(__file__).resolve().parents[7]
sys.path.insert(0, str(SRC))
sys.path.insert(0, str(REPO / "apps" / "data-pipeline"))

from build_panel import (  # noqa: E402
    MAX_CONTINUOUS_GAP_MINUTES,
    availability_timeseries,
    build_state_panel,
)
from load_snapshots import load_snapshot  # noqa: E402
from loop_paths import (  # noqa: E402
    EXTRACTED_CHARGER_INFO,
    EXTRACTED_DAILY,
    LOOP1_DIR,
    LOOP1_LOGS,
    LOOPS_ARCHIVE,
    iter_status_csvs,
)

OUT = REPO / "docs" / "data" / "analysis" / "snapshot_all_20260723"
FIG = OUT / "figures"
REPORT = REPO / "docs" / "보고" / "스냅샷_시각_신뢰도_20260723.md"

DAEGU = {"lat": (35.6, 36.05), "lng": (128.35, 128.85)}


def _style() -> None:
    plt.rcParams["font.family"] = ["Malgun Gothic", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False


def collect_unique_files() -> dict[str, Path]:
    """Prefer live loop1; then any from_lightsail_* archive (newest archive name first)."""
    dirs: list[tuple[int, Path]] = [(0, LOOP1_DIR / "snapshots")]
    if LOOPS_ARCHIVE.is_dir():
        for arch in sorted(LOOPS_ARCHIVE.glob("from_lightsail_*"), reverse=True):
            snap = arch / "loop1" / "snapshots"
            if snap.is_dir():
                # priority 1+ by reverse name order already; tie-break by path order
                dirs.append((1, snap))
    best: dict[str, tuple[int, Path]] = {}
    for pri, d in dirs:
        if not d.is_dir():
            continue
        for path in iter_status_csvs(d):
            sid = path.stem.replace("daegu_charger_status_", "")
            cur = best.get(sid)
            if cur is None or pri < cur[0]:
                best[sid] = (pri, path)
    return {sid: path for sid, (_, path) in best.items()}


def load_corpus() -> tuple[pd.DataFrame, pd.DataFrame]:
    unique = collect_unique_files()
    frames: list[pd.DataFrame] = []
    meta_rows: list[dict] = []
    for sid in sorted(unique.keys()):
        path = unique[sid]
        df = load_snapshot(path)
        df["snapshotId"] = sid
        df["stat"] = pd.to_numeric(df["stat"], errors="coerce")
        ts = pd.to_datetime(sid, format="%Y%m%d_%H%M%S")
        df["collectedAt"] = ts
        frames.append(df)
        meta_rows.append({"snapshot_id": sid, "ts": ts, "rows": len(df)})
    all_df = pd.concat(frames, ignore_index=True)
    meta = pd.DataFrame(meta_rows).sort_values("ts").reset_index(drop=True)
    meta["gap_min"] = meta["ts"].diff().dt.total_seconds() / 60
    return all_df, meta


def enrich_age(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["upd"] = pd.to_datetime(out["statUpdDt"], format="%Y%m%d%H%M%S", errors="coerce")
    out["fetched"] = pd.to_datetime(out.get("fetchedAt"), errors="coerce")
    # fallback: use collectedAt if fetchedAt missing
    miss = out["fetched"].isna()
    if miss.any():
        out.loc[miss, "fetched"] = out.loc[miss, "collectedAt"]
    out["age_min"] = (out["fetched"] - out["upd"]).dt.total_seconds() / 60
    out["rel_grade"] = pd.cut(
        out["age_min"],
        bins=[-np.inf, 5, 15, np.inf],
        labels=["HIGH", "NORMAL", "CHECK_REQUIRED"],
    )
    return out


def latest_info() -> pd.DataFrame | None:
    cands = sorted(EXTRACTED_CHARGER_INFO.glob("daegu_charger_info_*.csv"))
    cands += sorted(EXTRACTED_DAILY.glob("**/daegu_charger_info_*latest.csv"))
    if not cands:
        return None
    path = cands[-1]
    info = pd.read_csv(path, dtype={"statId": str})
    info["lat"] = pd.to_numeric(info["lat"], errors="coerce")
    info["lng"] = pd.to_numeric(info["lng"], errors="coerce")
    return info.dropna(subset=["lat", "lng"]).drop_duplicates("statId")


def latest_info_chargers() -> pd.DataFrame | None:
    """Charger-grain info (keep limitYn duplicates per station)."""
    cands = sorted(EXTRACTED_CHARGER_INFO.glob("daegu_charger_info_*service*.csv"))
    if not cands:
        cands = sorted(EXTRACTED_CHARGER_INFO.glob("daegu_charger_info_*.csv"))
    cands += sorted(EXTRACTED_DAILY.glob("**/daegu_charger_info_*latest.csv"))
    if not cands:
        return None
    # prefer service_latest if present
    prefer = [p for p in cands if "service_latest" in p.name]
    path = prefer[-1] if prefer else cands[-1]
    info = pd.read_csv(path, dtype=str, low_memory=False)
    if "statId" not in info.columns and "stat_id" in info.columns:
        info = info.rename(columns={"stat_id": "statId"})
    return info


def plot_availability(ats: pd.DataFrame) -> Path:
    fig, ax = plt.subplots(figsize=(14, 4.5), facecolor="#f7f8fa")
    ax.plot(ats["ts"], ats["availability_pct"], color="#18794e", linewidth=1.2)
    ax.axhline(ats["availability_pct"].mean(), color="#68737d", linestyle="--", linewidth=1)
    ax.set_title("패널 가용률 시계열 (전체 스냅샷)", loc="left", fontweight="bold", fontsize=14)
    ax.set_ylabel("가용률 (%)")
    ax.set_ylim(0, 100)
    ax.grid(alpha=0.25)
    ax.set_facecolor("#ffffff")
    ax.spines[["top", "right"]].set_visible(False)
    fig.text(
        0.06,
        0.02,
        f"mean={ats['availability_pct'].mean():.1f}% · gap>{MAX_CONTINUOUS_GAP_MINUTES}min resets segment · "
        "available/(available+in_use)",
        fontsize=8.5,
        color="#68737d",
    )
    out = FIG / "01_availability_timeseries.png"
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_gap_hist(meta: pd.DataFrame) -> Path:
    gaps = meta["gap_min"].dropna()
    gaps_c = gaps.clip(upper=60)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), facecolor="#f7f8fa")
    axes[0].hist(gaps_c, bins=40, color="#4c78a8", edgecolor="white")
    axes[0].axvline(5, color="#18794e", ls="--", lw=1.2, label="5분")
    axes[0].axvline(15, color="#e2b93b", ls="--", lw=1.2, label="15분")
    axes[0].axvline(25, color="#b24c63", ls="--", lw=1.2, label="25분(세그먼트)")
    axes[0].set_title("틱 간격 분포 (60분 이상 합산)", loc="left", fontweight="bold")
    axes[0].set_xlabel("gap (분)")
    axes[0].legend(fontsize=8)
    axes[0].grid(axis="y", alpha=0.25)

    big = meta.loc[meta["gap_min"] > 25, ["ts", "gap_min"]].copy()
    if len(big):
        axes[1].barh(big["ts"].astype(str), big["gap_min"], color="#b24c63")
        axes[1].set_title(f"25분 초과 공백 {len(big)}회", loc="left", fontweight="bold")
        axes[1].set_xlabel("gap (분)")
    else:
        axes[1].text(0.5, 0.5, "25분 초과 공백 없음", ha="center", va="center")
        axes[1].set_axis_off()
    for ax in axes:
        ax.set_facecolor("#ffffff")
        ax.spines[["top", "right"]].set_visible(False)
    out = FIG / "02_gap_distribution.png"
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_by_date(meta: pd.DataFrame, ats: pd.DataFrame) -> Path:
    meta = meta.copy()
    meta["date"] = meta["ts"].dt.date.astype(str)
    counts = meta.groupby("date").size()
    ats = ats.copy()
    ats["date"] = ats["ts"].dt.date.astype(str)
    avail = ats.groupby("date")["availability_pct"].mean()

    fig, axes = plt.subplots(2, 1, figsize=(12, 7), facecolor="#f7f8fa", sharex=True)
    axes[0].bar(counts.index.astype(str), counts.values, color="#4c78a8")
    axes[0].set_title("일자별 스냅샷 수", loc="left", fontweight="bold")
    axes[0].set_ylabel("스냅샷")
    axes[1].plot(avail.index.astype(str), avail.values, marker="o", color="#18794e", lw=2)
    axes[1].set_title("일자별 패널 가용률 평균", loc="left", fontweight="bold")
    axes[1].set_ylabel("가용률 (%)")
    axes[1].set_ylim(0, 100)
    for ax in axes:
        ax.grid(alpha=0.25)
        ax.set_facecolor("#ffffff")
        ax.spines[["top", "right"]].set_visible(False)
    plt.xticks(rotation=30, ha="right")
    out = FIG / "03_by_date.png"
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_hourly_heatmap(ats: pd.DataFrame) -> Path:
    ats = ats.copy()
    ats["date"] = ats["ts"].dt.date.astype(str)
    ats["hour"] = ats["ts"].dt.hour
    pivot = ats.pivot_table(index="date", columns="hour", values="availability_pct", aggfunc="mean")
    # ensure 0..23 columns so missing hours show as 미수집
    pivot = pivot.reindex(columns=list(range(24)))
    data = np.ma.masked_invalid(pivot.to_numpy(dtype=float))
    cmap = plt.get_cmap("RdYlGn").copy()
    cmap.set_bad("#e8e8e8")  # 미수집(그날 그 시 스냅 없음)
    fig, ax = plt.subplots(figsize=(14, 4.5), facecolor="#f7f8fa")
    im = ax.imshow(data, aspect="auto", cmap=cmap, vmin=30, vmax=90)
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels(pivot.index)
    ax.set_xticks(range(24))
    ax.set_xticklabels(list(range(24)))
    ax.set_title("시간대×일자 패널 가용률 히트맵 (회색=미수집)", loc="left", fontweight="bold")
    ax.set_xlabel("시 (KST)")
    fig.colorbar(im, ax=ax, fraction=0.02, pad=0.02, label="%")
    out = FIG / "04_hourly_heatmap.png"
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_hourly_union_profile(ats: pd.DataFrame) -> Path:
    """묘수: 일자에 구멍이 있어도 같은 시각끼리 모아 0~23시를 한 번에 본다."""
    d = ats.dropna(subset=["availability_pct"]).copy()
    d["hour"] = d["ts"].dt.hour
    d["date"] = d["ts"].dt.date.astype(str)
    g = (
        d.groupby("hour", as_index=False)
        .agg(
            mean_pct=("availability_pct", "mean"),
            median_pct=("availability_pct", "median"),
            ticks=("availability_pct", "size"),
            days=("date", "nunique"),
        )
        .set_index("hour")
        .reindex(range(24))
    )
    g.to_csv(OUT / "availability_by_hour_union.csv", encoding="utf-8-sig")

    fig, ax1 = plt.subplots(figsize=(13, 4.8), facecolor="#f7f8fa")
    ax1.set_facecolor("#ffffff")
    hours = np.arange(24)
    ax1.fill_between(hours, g["mean_pct"], alpha=0.25, color="#18794e")
    ax1.plot(hours, g["mean_pct"], color="#18794e", lw=2.4, marker="o", ms=5, label="평균 %")
    ax1.plot(hours, g["median_pct"], color="#4c78a8", lw=1.6, ls="--", marker=".", label="중앙값 %")
    ax1.set_xticks(hours)
    ax1.set_xlim(-0.5, 23.5)
    ax1.set_ylim(0, 100)
    ax1.set_ylabel("가용률 (%)")
    ax1.set_xlabel("시 (KST) — 모든 일자 합집합")
    ax1.set_title(
        "시간대 합집합 프로파일 (날짜 구멍 무시 · 0~23시 한눈에)",
        loc="left",
        fontweight="bold",
    )
    ax1.grid(axis="y", alpha=0.25)
    ax1.spines[["top", "right"]].set_visible(False)

    ax2 = ax1.twinx()
    ax2.bar(hours, g["ticks"].fillna(0), width=0.55, color="#c8cdd3", alpha=0.55, label="틱 수")
    ax2.set_ylabel("관측 틱 수")
    ax2.spines[["top"]].set_visible(False)

    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, loc="lower right", frameon=False)
    ax1.text(
        0.01,
        -0.18,
        "해석: 회색 막대=그 시각에 모인 스냅 수 · 선=그 시각들의 패널 가용률. "
        "특정 날짜 공백은 히트맵(04)에서 확인.",
        transform=ax1.transAxes,
        fontsize=9,
        color="#555",
    )
    out = FIG / "08_hourly_union_profile.png"
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return out


def _station_segment_flags(info: pd.DataFrame) -> pd.DataFrame:
    """Same policy as D1: limitYn any-Y = restricted; name heuristic advisory."""
    raw = info.copy()
    if "statId" not in raw.columns and "stat_id" in raw.columns:
        raw = raw.rename(columns={"stat_id": "statId"})
    raw["statId"] = raw["statId"].astype(str)
    lim = raw["limitYn"].astype(str).str.upper().eq("Y") if "limitYn" in raw.columns else False
    # charger-grain → station any-Y
    if isinstance(lim, pd.Series) and lim.index.equals(raw.index):
        restricted = raw.assign(_lim=lim).groupby("statId")["_lim"].any()
    else:
        restricted = pd.Series(False, index=raw["statId"].unique())
    st = raw.drop_duplicates("statId").set_index("statId")
    name_blob = (
        st.get("statNm", pd.Series("", index=st.index)).fillna("").astype(str)
        + " "
        + st.get("addr", pd.Series("", index=st.index)).fillna("").astype(str)
    )
    residential = name_blob.str.contains(
        r"아파트|단지|\bAPT\b|거주자", case=False, na=False, regex=True
    )
    out = pd.DataFrame(
        {
            "access_restricted": restricted.reindex(st.index).fillna(False).astype(bool),
            "name_suggests_residential": residential.astype(bool),
        }
    )
    out["recommend_public_default"] = ~out["access_restricted"]
    out["residential_or_restricted"] = (
        out["access_restricted"] | out["name_suggests_residential"]
    )
    return out.reset_index()


def _ats_for_stat_ids(panel: pd.DataFrame, stat_ids: set[str]) -> pd.DataFrame:
    cols = [c for c in panel.columns if str(c).split("|", 1)[0] in stat_ids]
    if not cols:
        return pd.DataFrame(columns=["ts", "availability_pct", "usable_known"])
    sub = panel[cols]
    avail = (sub == 2).sum(axis=1)
    in_use = (sub == 3).sum(axis=1)
    known = avail + in_use
    pct = np.where(known > 0, avail / known * 100.0, np.nan)
    return pd.DataFrame(
        {
            "ts": sub.index,
            "availability_pct": pct,
            "usable_known": known.to_numpy(),
            "chargers_in_segment": len(cols),
        }
    )


def _hour_profile(ats: pd.DataFrame) -> pd.DataFrame:
    d = ats.dropna(subset=["availability_pct"]).copy()
    if d.empty:
        return pd.DataFrame(
            {"hour": range(24), "mean_pct": np.nan, "ticks": 0}
        ).set_index("hour")
    d["hour"] = d["ts"].dt.hour
    return (
        d.groupby("hour")
        .agg(mean_pct=("availability_pct", "mean"), ticks=("availability_pct", "size"))
        .reindex(range(24))
    )


def plot_hourly_public_vs_residential(
    panel: pd.DataFrame, info: pd.DataFrame | None
) -> Path | None:
    """공용 후보 vs 주거·이용제한 — 시간대 가용률 비교 (아파트 등 특수 요소)."""
    if info is None or panel is None or panel.empty:
        return None
    flags = _station_segment_flags(info)
    public_ids = set(
        flags.loc[flags["recommend_public_default"], "statId"].astype(str)
    )
    special_ids = set(
        flags.loc[flags["residential_or_restricted"], "statId"].astype(str)
    )
    # residential-name only (may overlap restricted) — thin advisory line
    apt_ids = set(
        flags.loc[flags["name_suggests_residential"], "statId"].astype(str)
    )

    ats_pub = _ats_for_stat_ids(panel, public_ids)
    ats_spc = _ats_for_stat_ids(panel, special_ids)
    ats_apt = _ats_for_stat_ids(panel, apt_ids)
    hp = _hour_profile(ats_pub).rename(columns={"mean_pct": "public_pct", "ticks": "public_ticks"})
    hs = _hour_profile(ats_spc).rename(
        columns={"mean_pct": "special_pct", "ticks": "special_ticks"}
    )
    ha = _hour_profile(ats_apt).rename(columns={"mean_pct": "apt_name_pct", "ticks": "apt_ticks"})
    merged = hp.join(hs, how="outer").join(ha, how="outer")
    merged.to_csv(OUT / "availability_by_hour_public_vs_residential.csv", encoding="utf-8-sig")

    n_pub_ch = int(ats_pub["chargers_in_segment"].iloc[0]) if len(ats_pub) else 0
    n_spc_ch = int(ats_spc["chargers_in_segment"].iloc[0]) if len(ats_spc) else 0
    n_apt_ch = int(ats_apt["chargers_in_segment"].iloc[0]) if len(ats_apt) else 0

    fig, ax = plt.subplots(figsize=(13, 5.0), facecolor="#f7f8fa")
    ax.set_facecolor("#ffffff")
    hours = np.arange(24)
    ax.plot(
        hours,
        merged["public_pct"],
        color="#18794e",
        lw=2.6,
        marker="o",
        ms=5,
        label=f"공용 후보 (limitYn 전부 N) · 충전기≈{n_pub_ch}",
    )
    ax.plot(
        hours,
        merged["special_pct"],
        color="#b24c63",
        lw=2.4,
        marker="s",
        ms=4.5,
        label=f"주거·이용제한 (limitYn=Y 또는 이름 아파트/단지) · ≈{n_spc_ch}",
    )
    ax.plot(
        hours,
        merged["apt_name_pct"],
        color="#e2b93b",
        lw=1.5,
        ls="--",
        marker=".",
        ms=4,
        label=f"이름 휴리스틱만 (아파트/단지/APT) · ≈{n_apt_ch}",
    )
    ax.set_xticks(hours)
    ax.set_xlim(-0.5, 23.5)
    ax.set_ylim(0, 100)
    ax.set_ylabel("패널 가용률 (%)")
    ax.set_xlabel("시 (KST) — 일자 합집합")
    ax.set_title(
        "시간대 가용률 · 공용 vs 주거·이용제한",
        loc="left",
        fontweight="bold",
    )
    ax.grid(axis="y", alpha=0.25)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(loc="lower left", frameon=False, fontsize=9)
    ax.text(
        0.01,
        -0.20,
        "정책: D1과 동일 — access_restricted=소내 limitYn=Y 1대라도 있음 · "
        "recommend_public_default=~restricted · 이름 휴리스틱은 참고만. "
        "점수/제외 확정은 ②.",
        transform=ax.transAxes,
        fontsize=8.5,
        color="#555",
    )
    out = FIG / "09_hourly_public_vs_residential.png"
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_reliability(df: pd.DataFrame) -> Path:
    age = df["age_min"].dropna()
    age = age[(age >= -1) & (age <= 24 * 60)]
    high = int((age < 5).sum())
    normal = int(((age >= 5) & (age < 15)).sum())
    check = int((age >= 15).sum())
    total = max(high + normal + check, 1)

    fig, axes = plt.subplots(1, 2, figsize=(13, 5), facecolor="#f7f8fa")
    labels = ["HIGH\n(<5분)", "NORMAL\n(5~15)", "CHECK\n(15+)"]
    vals = [high, normal, check]
    colors = ["#18794e", "#e2b93b", "#b24c63"]
    bars = axes[0].bar(labels, vals, color=colors)
    for b, v in zip(bars, vals):
        axes[0].text(
            b.get_x() + b.get_width() / 2,
            v,
            f"{v / total * 100:.1f}%",
            ha="center",
            va="bottom",
            fontweight="bold",
        )
    axes[0].set_title("신뢰도 등급 (fetchedAt − statUpdDt)", loc="left", fontweight="bold")
    axes[0].set_ylabel("관측 행")

    capped = age.clip(upper=60)
    axes[1].hist(capped, bins=30, color="#4c78a8", edgecolor="white")
    axes[1].axvline(5, color="#18794e", ls="--")
    axes[1].axvline(15, color="#b24c63", ls="--")
    axes[1].set_title("경과시간 분포 (60분+ 합산)", loc="left", fontweight="bold")
    axes[1].set_xlabel("분")
    for ax in axes:
        ax.grid(axis="y", alpha=0.25)
        ax.set_facecolor("#ffffff")
        ax.spines[["top", "right"]].set_visible(False)
    out = FIG / "05_reliability_grades.png"
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_reliability_by_day(df: pd.DataFrame) -> Path:
    d = df.dropna(subset=["rel_grade", "collectedAt"]).copy()
    d["date"] = d["collectedAt"].dt.date.astype(str)
    share = (
        d.groupby(["date", "rel_grade"], observed=True)
        .size()
        .unstack(fill_value=0)
    )
    share = share.div(share.sum(axis=1), axis=0) * 100
    for col in ["HIGH", "NORMAL", "CHECK_REQUIRED"]:
        if col not in share.columns:
            share[col] = 0
    share = share[["HIGH", "NORMAL", "CHECK_REQUIRED"]]

    fig, ax = plt.subplots(figsize=(12, 4.5), facecolor="#f7f8fa")
    bottom = np.zeros(len(share))
    colors = {"HIGH": "#18794e", "NORMAL": "#e2b93b", "CHECK_REQUIRED": "#b24c63"}
    x = np.arange(len(share))
    for col in share.columns:
        ax.bar(x, share[col].values, bottom=bottom, color=colors[col], label=col)
        bottom += share[col].values
    ax.set_xticks(x)
    ax.set_xticklabels(share.index, rotation=30, ha="right")
    ax.set_ylim(0, 100)
    ax.set_ylabel("비율 (%)")
    ax.set_title("일자별 신뢰도 등급 구성", loc="left", fontweight="bold")
    ax.legend(loc="upper right")
    ax.set_facecolor("#ffffff")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.25)
    out = FIG / "06_reliability_by_day.png"
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_coverage(df: pd.DataFrame, info: pd.DataFrame | None) -> Path | None:
    if info is None:
        return None
    info = info[
        info["lat"].between(*DAEGU["lat"]) & info["lng"].between(*DAEGU["lng"])
    ].copy()
    seen = set(df["statId"].astype(str).unique())
    info["observed"] = info["statId"].isin(seen)
    fig, ax = plt.subplots(figsize=(8.5, 8.5), facecolor="#f7f8fa")
    miss = info[~info["observed"]]
    hit = info[info["observed"]]
    ax.scatter(miss["lng"], miss["lat"], s=8, c="#c8d0d8", alpha=0.55, label=f"미관측 {len(miss):,}")
    ax.scatter(hit["lng"], hit["lat"], s=10, c="#18794e", alpha=0.65, label=f"관측 {len(hit):,}")
    ax.set_title("충전소 관측 커버리지", loc="left", fontweight="bold")
    ax.legend(loc="upper right")
    ax.set_aspect("equal", adjustable="datalim")
    ax.grid(alpha=0.2)
    pct = len(hit) / len(info) * 100 if len(info) else 0
    fig.text(0.06, 0.02, f"관측 {len(hit):,} / {len(info):,} ({pct:.1f}%)", fontsize=8.5, color="#68737d")
    out = FIG / "07_coverage_map.png"
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return out


def reliability_checks(df: pd.DataFrame, meta: pd.DataFrame, ats: pd.DataFrame) -> dict:
    age = df["age_min"]
    age_ok = age.dropna()
    age_ok = age_ok[(age_ok >= -1) & (age_ok <= 24 * 60)]
    grades = df["rel_grade"].value_counts(dropna=False).to_dict()
    grades = {str(k): int(v) for k, v in grades.items()}

    gaps = meta["gap_min"].dropna()
    n_big = int((gaps > 25).sum())
    # continuous segments
    seg = (meta["ts"].diff().gt(pd.Timedelta(minutes=25))).cumsum()
    n_seg = int(seg.nunique())

    # negative age = clock skew / bad parse
    n_neg = int((age < -1).sum())
    n_missing_upd = int(df["upd"].isna().sum())

    call_ok = call_n = call_skip = None
    call_path = LOOP1_LOGS / "call_log.jsonl"
    if call_path.exists():
        ok = attempted = skipped = 0
        for line in call_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            # daily_limit_margin 등 의도적 skip은 API 실패가 아님 → R1 분모에서 제외
            if rec.get("skipped") is True or rec.get("reason") == "daily_limit_margin":
                skipped += 1
                continue
            attempted += 1
            if rec.get("ok") is True or rec.get("http_status") == 200:
                ok += 1
        call_ok, call_n, call_skip = ok, attempted, skipped

    # per-day HIGH share
    d = df.dropna(subset=["rel_grade"]).copy()
    d["date"] = d["collectedAt"].dt.date.astype(str)
    high_share = (
        d.assign(is_high=d["rel_grade"].astype(str) == "HIGH")
        .groupby("date")["is_high"]
        .mean()
        .mul(100)
        .round(1)
        .to_dict()
    )

    r1_detail = (
        f"{call_ok}/{call_n} attempted"
        + (f" · skip(quota)={call_skip}" if call_skip else "")
        if call_n is not None
        else "live log 없음(archive만 포함 가능)"
    )
    checks = [
        {
            "id": "R1_call_log",
            "name": "live call_log 성공률 (시도분만 · quota skip 제외)",
            "pass": (call_n is None) or (call_n > 0 and call_ok == call_n),
            "detail": r1_detail,
        },
        {
            "id": "R2_gap25",
            "name": "25분 초과 공백 ≤10회 (PC off 허용)",
            "pass": n_big <= 10,
            "detail": f"{n_big}회 · 세그먼트 {n_seg}개",
        },
        {
            "id": "R3_age_median",
            "name": "statUpdDt 경과 중앙값 ≤10분",
            "pass": float(age_ok.median()) <= 10 if len(age_ok) else False,
            "detail": f"median={float(age_ok.median()):.2f} · p95={float(age_ok.quantile(0.95)):.2f}",
        },
        {
            "id": "R4_high_share",
            "name": "HIGH 등급 비율 ≥50%",
            "pass": (grades.get("HIGH", 0) / max(sum(v for k, v in grades.items() if k != 'nan'), 1)) >= 0.5,
            "detail": str(grades),
        },
        {
            "id": "R5_parse",
            "name": "statUpdDt 파싱 실패·음수 age 소수",
            "pass": (n_missing_upd / max(len(df), 1) < 0.01) and (n_neg / max(len(df), 1) < 0.01),
            "detail": f"missing_upd={n_missing_upd} · neg_age={n_neg}",
        },
        {
            "id": "R6_panel_avail",
            "name": "패널 가용률 시계열 산출 가능",
            "pass": len(ats.dropna(subset=["availability_pct"])) > 100,
            "detail": f"ticks={len(ats)} · mean={float(ats['availability_pct'].mean()):.1f}%",
        },
    ]

    return {
        "grades": grades,
        "age_median": float(age_ok.median()) if len(age_ok) else None,
        "age_p95": float(age_ok.quantile(0.95)) if len(age_ok) else None,
        "gaps_gt25": n_big,
        "segments": n_seg,
        "high_share_by_date": high_share,
        "checks": checks,
        "pass_count": sum(1 for c in checks if c["pass"]),
        "check_count": len(checks),
    }


def main() -> int:
    _style()
    FIG.mkdir(parents=True, exist_ok=True)
    print("loading corpus...")
    all_df, meta = load_corpus()
    print(f"snapshots={len(meta)} rows={len(all_df)}")
    all_df = enrich_age(all_df)

    print("panel...")
    panel = build_state_panel(all_df)
    ats = availability_timeseries(panel)

    info = latest_info()
    figs = [
        plot_availability(ats),
        plot_gap_hist(meta),
        plot_by_date(meta, ats),
        plot_hourly_heatmap(ats),
        plot_reliability(all_df),
        plot_reliability_by_day(all_df),
    ]
    cov = plot_coverage(all_df, info)
    if cov:
        figs.append(cov)
    figs.append(plot_hourly_union_profile(ats))
    seg = plot_hourly_public_vs_residential(panel, latest_info_chargers())
    if seg:
        figs.append(seg)

    rel = reliability_checks(all_df, meta, ats)
    (OUT / "reliability_checks.json").write_text(
        json.dumps(rel, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )

    # grade by date table
    d = all_df.dropna(subset=["rel_grade"]).copy()
    d["date"] = d["collectedAt"].dt.date.astype(str)
    grade_day = (
        d.groupby(["date", "rel_grade"], observed=True)
        .size()
        .unstack(fill_value=0)
    )
    grade_day.to_csv(OUT / "reliability_by_date.csv", encoding="utf-8-sig")

    lines = [
        "# status 스냅샷 — 시각자료 · 신뢰도 체크 (2026-07-23)",
        "",
        f"- 기반: [`스냅샷_전체분석_20260723.md`](./스냅샷_전체분석_20260723.md)",
        f"- 스냅샷 **{len(meta)}** · 이벤트 행 **{len(all_df):,}**",
        f"- 신뢰도 체크 **{rel['pass_count']}/{rel['check_count']} PASS**",
        "",
        "## 1. 시각자료",
        "",
    ]
    captions = {
        "01_availability_timeseries.png": "패널 가용률 시계열",
        "02_gap_distribution.png": "틱 간격 · 25분 초과 공백",
        "03_by_date.png": "일자별 스냅샷 수 · 가용률",
        "04_hourly_heatmap.png": "시간대×일자 가용률 히트맵 (회색=미수집)",
        "05_reliability_grades.png": "신뢰도 등급 · 경과시간 분포",
        "06_reliability_by_day.png": "일자별 신뢰도 구성",
        "07_coverage_map.png": "충전소 관측 커버리지",
        "08_hourly_union_profile.png": "시간대 합집합 프로파일 (0~23시 한눈에)",
        "09_hourly_public_vs_residential.png": "시간대 가용률 · 공용 vs 주거·이용제한",
    }
    for p in figs:
        name = p.name
        rel_path = p.relative_to(REPO).as_posix()
        lines += [f"### {captions.get(name, name)}", "", f"![{name}]({rel_path})", ""]

    lines += [
        "## 2. 신뢰도 체크리스트",
        "",
        "| ID | 항목 | 결과 | 상세 |",
        "|---|---|---|---|",
    ]
    for c in rel["checks"]:
        mark = "PASS" if c["pass"] else "FAIL"
        lines.append(f"| {c['id']} | {c['name']} | **{mark}** | {c['detail']} |")

    lines += [
        "",
        "### 요약 수치",
        "",
        f"- age(fetched−statUpdDt) 중앙값 **{rel['age_median']:.2f}분** · P95 **{rel['age_p95']:.2f}분**",
        f"- 등급 카운트: `{rel['grades']}`",
        f"- gap>25분 **{rel['gaps_gt25']}회** · 연속 세그먼트 **{rel['segments']}개**",
        "",
        "## 3. 파일",
        "",
        f"- 그림: `{FIG.relative_to(REPO).as_posix()}/`",
        f"- JSON: `{ (OUT / 'reliability_checks.json').relative_to(REPO).as_posix() }`",
        f"- 일자×등급: `{ (OUT / 'reliability_by_date.csv').relative_to(REPO).as_posix() }`",
        "",
        "```",
        "DA➀ | snapshot charts + reliability | 2026-07-23",
        "```",
        "",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"pass": f"{rel['pass_count']}/{rel['check_count']}", "figs": [str(p) for p in figs]}, ensure_ascii=False, indent=2))
    print(f"WROTE {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
