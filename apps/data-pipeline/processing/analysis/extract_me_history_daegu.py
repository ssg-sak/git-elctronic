"""Extract Daegu rows from ME/Climate EV charging-history Excel dumps + report.

Usage (repo root):
  python apps/data-pipeline/processing/analysis/extract_me_history_daegu.py
"""
from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

KST = ZoneInfo("Asia/Seoul")
DOWNLOADS = Path(r"C:\Users\PC\Downloads")
REPO = Path(__file__).resolve().parents[4]

plt.rcParams["font.family"] = ["Malgun Gothic", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

# Files explicitly named by user (filename stem contains month label)
FILE_GLOBS = [
    "20251104 2025년10월*충전이력*.xlsx",
    "20251202 2025년11월*충전이력*.xlsx",
    "20260105 2025년12월*충전이력*.xlsx",
    "20260203 2026년1월*충전이력*.xlsx",
    "20260306 2026년2월*충전이력*.xlsx",
    "20260402 2026년3월*충전이력*.xlsx",
    "20260504 2026년4월*충전이력*.xlsx",
    "20260601 2026년5월*충전이력*.xlsx",
]

MONTH_RE = re.compile(r"(20\d{2})년\s*(\d{1,2})월")


def resolve_files() -> list[Path]:
    found: list[Path] = []
    for g in FILE_GLOBS:
        hits = list(DOWNLOADS.glob(g))
        if not hits:
            # fallback loose match
            continue
        found.append(hits[0])
    if len(found) < 8:
        # also pick any matching 충전이력 in Downloads listed by user pattern
        extra = sorted(DOWNLOADS.glob("*충전이력(상세내역).xlsx"))
        for p in extra:
            if p not in found:
                found.append(p)
    return sorted(set(found), key=lambda p: p.name)


def month_label_from_name(name: str) -> str:
    m = MONTH_RE.search(name)
    if not m:
        return "unknown"
    return f"{m.group(1)}-{int(m.group(2)):02d}"


def parse_duration_to_minutes(s: pd.Series) -> pd.Series:
    """HH:MM:SS or timedelta-like → minutes."""
    def one(v):
        if pd.isna(v):
            return np.nan
        if isinstance(v, (int, float)):
            return float(v)
        t = str(v).strip()
        if not t or t.lower() == "nan":
            return np.nan
        parts = t.split(":")
        try:
            if len(parts) == 3:
                h, m, sec = map(float, parts)
                return h * 60 + m + sec / 60.0
            if len(parts) == 2:
                m, sec = map(float, parts)
                return m + sec / 60.0
        except ValueError:
            return np.nan
        return np.nan

    return s.map(one)


def is_daegu(df: pd.DataFrame) -> pd.Series:
    """Keep only 대구광역시. Reject null/empty and false '대구' hits
    (광주대구고속도로, 서대구일로, 강진군 대구면, …)."""
    region = (
        df["지역"].fillna("").astype(str).str.strip()
        if "지역" in df.columns
        else pd.Series("", index=df.index)
    )
    addr = (
        df["주소"].fillna("").astype(str).str.strip()
        if "주소" in df.columns
        else pd.Series("", index=df.index)
    )
    # require both region and address to be 대구광역시 (no substring shortcuts)
    return (region == "대구광역시") & addr.str.startswith("대구광역시")


def load_daegu(path: Path) -> pd.DataFrame:
    print(f"READ {path.name} ...", flush=True)
    df = pd.read_excel(path, sheet_name=0, dtype=str)
    n0 = len(df)
    mask = is_daegu(df)
    out = df.loc[mask].copy()
    out["source_file"] = path.name
    out["month"] = month_label_from_name(path.name)
    print(f"  rows {n0:,} → daegu {len(out):,}", flush=True)
    return out


def enrich(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d["충전량_num"] = pd.to_numeric(d.get("충전량"), errors="coerce")
    d["충전분"] = parse_duration_to_minutes(d.get("충전시간", pd.Series(dtype=str)))
    # start datetime
    start = d.get("충전시작일시")
    d["start_ts"] = pd.to_datetime(start, format="%Y%m%d%H%M%S", errors="coerce")
    # some may already be datetime strings
    if d["start_ts"].isna().mean() > 0.5:
        d["start_ts"] = pd.to_datetime(start, errors="coerce")
    d["hour"] = d["start_ts"].dt.hour
    d["dow"] = d["start_ts"].dt.dayofweek  # 0=Mon
    d["is_weekend"] = d["dow"] >= 5
    d["station_key"] = (
        d["충전소명"].astype(str).str.strip()
        + "|"
        + d.get("시군구", pd.Series("", index=d.index)).astype(str).str.strip()
    )
    return d


def plot_monthly(d: pd.DataFrame, fig_dir: Path) -> Path:
    g = (
        d.groupby("month", as_index=False)
        .agg(
            sessions=("충전소명", "size"),
            kwh=("충전량_num", "sum"),
            stations=("station_key", "nunique"),
        )
        .sort_values("month")
    )
    fig, axes = plt.subplots(2, 1, figsize=(11, 6.5), sharex=True, facecolor="#f7f8fa")
    for ax in axes:
        ax.set_facecolor("#ffffff")
        ax.grid(axis="y", alpha=0.25)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].bar(g["month"], g["sessions"], color="#4c78a8")
    axes[0].set_ylabel("충전 세션 수")
    axes[0].set_title("대구 · 월별 충전 세션 (환경부/기후부 상세이력)", loc="left", fontweight="bold")
    axes[1].bar(g["month"], g["kwh"] / 1000.0, color="#54a24b")
    axes[1].set_ylabel("충전량 (MWh)")
    axes[1].set_xlabel("월")
    fig.autofmt_xdate(rotation=30)
    out = fig_dir / "01_monthly_sessions_kwh.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    g.to_csv(fig_dir.parent / "monthly_summary.csv", index=False, encoding="utf-8-sig")
    return out


def plot_hourly(d: pd.DataFrame, fig_dir: Path) -> Path:
    h = d.dropna(subset=["hour"]).groupby("hour").size()
    h = h.reindex(range(24), fill_value=0)
    fig, ax = plt.subplots(figsize=(11, 4.2), facecolor="#f7f8fa")
    ax.set_facecolor("#ffffff")
    ax.bar(h.index, h.values, color="#f58518")
    ax.set_xticks(range(24))
    ax.set_xlabel("시 (시작 시각)")
    ax.set_ylabel("세션 수")
    ax.set_title("대구 · 시간대별 충전 시작 (전체 월 합)", loc="left", fontweight="bold")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.25)
    out = fig_dir / "02_hourly_start.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_district(d: pd.DataFrame, fig_dir: Path) -> Path:
    g = d["시군구"].fillna("(미상)").astype(str).value_counts().head(10)
    fig, ax = plt.subplots(figsize=(9, 4.8), facecolor="#f7f8fa")
    ax.set_facecolor("#ffffff")
    ax.barh(g.index[::-1], g.values[::-1], color="#72b7b2")
    ax.set_xlabel("세션 수")
    ax.set_title("대구 · 시군구별 충전 세션 Top10", loc="left", fontweight="bold")
    ax.spines[["top", "right"]].set_visible(False)
    out = fig_dir / "03_district_sessions.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_type(d: pd.DataFrame, fig_dir: Path) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6), facecolor="#f7f8fa")
    for ax in axes:
        ax.set_facecolor("#ffffff")
        ax.spines[["top", "right"]].set_visible(False)
    big = d["충전소 유형(대분류)"].fillna("미상").value_counts().head(8)
    axes[0].barh(big.index[::-1], big.values[::-1], color="#b279a2")
    axes[0].set_title("충전소 유형(대분류)", loc="left", fontweight="bold")
    cap = d["충전기용량(KW)"].fillna("미상").astype(str).value_counts().head(8)
    axes[1].barh(cap.index[::-1], cap.values[::-1], color="#e45756")
    axes[1].set_title("충전기용량(KW) Top", loc="left", fontweight="bold")
    out = fig_dir / "04_station_type_capacity.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_weekend(d: pd.DataFrame, fig_dir: Path) -> Path:
    sub = d.dropna(subset=["is_weekend"])
    g = sub.groupby(sub["is_weekend"].map({True: "주말", False: "평일"})).agg(
        sessions=("충전소명", "size"),
        kwh_mean=("충전량_num", "mean"),
        min_mean=("충전분", "mean"),
    )
    fig, ax = plt.subplots(figsize=(7, 4.2), facecolor="#f7f8fa")
    ax.set_facecolor("#ffffff")
    ax.bar(g.index, g["sessions"], color=["#4c78a8", "#f58518"])
    ax.set_ylabel("세션 수")
    ax.set_title("대구 · 평일 vs 주말 세션", loc="left", fontweight="bold")
    ax.spines[["top", "right"]].set_visible(False)
    out = fig_dir / "05_weekday_weekend.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


def write_report(out: Path, summary: dict, figs: list[Path]) -> None:
    lines = [
        "# 환경부·기후부 충전이력 — 대구 추출 · 분석 의미 보고",
        "",
        "| | |",
        "|---|---|",
        f"| **생성** | {summary['generated_at']} |",
        f"| **원천** | 환경부/기후부 충전기 충전이력(상세내역) xlsx × {summary['n_files']} |",
        f"| **기간(파일)** | {summary['month_min']} ~ {summary['month_max']} |",
        f"| **필터** | `지역`=대구광역시 **그리고** `주소`가 대구광역시로 시작 · 결측/타시도 제외 |",
        f"| **대구 세션** | **{summary['daegu_sessions']:,}** |",
        f"| **충전소(이름+시군구)** | **{summary['stations']:,}** |",
        f"| **총 충전량** | **{summary['kwh_total']:,.0f} kWh** (~{summary['kwh_total']/1000:,.1f} MWh) |",
        "",
        "---",
        "",
        "## 1. 이 데이터가 뭐냐",
        "",
        "공공(환경부→기후부) **급속·공용 쪽 충전이력 상세**다. 한 행 = 충전 **1세션**.",
        "우리가 루프로 받는 EvCharger **실시간 상태(stat)** 와는 다르다.",
        "",
        "| | 충전이력(이번) | EvCharger status(루프) |",
        "|---|---|---|",
        "| 시점 | **끝난 충전**의 시작·종료·kWh | **지금** 가능/충전중 |",
        "| 주기 | 월별 공표 파일 | 5~10분 스냅 |",
        "| SafeCharge 용도 | **이용강도·시간대 수요** 보조 | **지금 갈 수 있나** |",
        "",
        "---",
        "",
        "## 2. 왜 모으고 대구만 뽑나",
        "",
        "1. **추천·점수(②)에 과거 이용 신호**를 줄 수 있다 — `usage_level`과 같은 계열.  ",
        "2. **시간대 프로파일** — 언제 충전이 몰리는지 (가용률·혼잡과 나란히 보면 ‘출발 창’).  ",
        "3. **시군구·시설유형** — 공영주차·공공·휴게 등 어디가 바쁜지.  ",
        "4. 실시간 미관측·낡은 status일 때 **‘평소에 바쁜 곳’** 보정용 (실시간 덮어쓰기 금지).",
        "",
        "전국 파일은 수십 MB×여러 달이라 **대구만** 남겨야 파이프·깃·분석이 감당 가능하다.",
        "",
        "---",
        "",
        "## 3. 이번 추출 요약 숫자",
        "",
        f"- 월 수: **{summary['n_months']}** ({', '.join(summary['months'])})  ",
        f"- 세션/월 median: **{summary['sessions_per_month_median']:,.0f}**  ",
        f"- 세션당 충전량 평균: **{summary['kwh_mean']:.2f} kWh** · 중앙 **{summary['kwh_median']:.2f}**  ",
        f"- 세션당 충전시간 평균: **{summary['min_mean']:.1f}분** (파싱된 행 기준)  ",
        f"- 시군구 Top: `{summary['top_districts']}`  ",
        f"- 유형 Top: `{summary['top_types']}`  ",
        "",
        "---",
        "",
        "## 4. 그림",
        "",
    ]
    caps = {
        "01_monthly_sessions_kwh.png": "월별 세션·충전량",
        "02_hourly_start.png": "시간대별 시작",
        "03_district_sessions.png": "시군구",
        "04_station_type_capacity.png": "유형·용량",
        "05_weekday_weekend.png": "평일/주말",
    }
    for p in figs:
        lines += [
            f"### {p.name}",
            "",
            f"![{caps.get(p.name, p.name)}](figures/{p.name})",
            "",
            f"**{caps.get(p.name, p.name)}**",
            "",
        ]

    lines += [
        "---",
        "",
        "## 5. SafeCharge에 붙이는 의미 (①→②)",
        "",
        "| 활용 | 의미 | 주의 |",
        "|---|---|---|",
        "| 월·시간대 수요 | ‘언제 바쁜 도시인가’ | 공표 급속 위주 → **완속·아파트 과소** 가능 |",
        "| 소별 세션 강도 | usage_level 보강·검증 | 충전소명 조인 ≠ 항상 `statId` |",
        "| 평일/주말 | 관광·시내 패턴 | 인과 단정 금지 |",
        "| 시설유형 | 공영주차 vs 공공기관 | EvCharger limitYn과 별개 |",
        "",
        "**하지 말 것:** 이력 kWh로 실시간 `available_count` 덮어쓰기.",
        "",
        "---",
        "",
        "## 6. 산출 파일",
        "",
        "| 파일 | 내용 |",
        "|---|---|",
        "| `daegu_me_history_all.csv` | 대구 전체 세션 |",
        "| `daegu_me_history_YYYY-MM.csv` | 월별 |",
        "| `monthly_summary.csv` | 월 집계 |",
        "| `station_intensity.csv` | 소별 세션·kWh |",
        "| `summary.json` | 메타 |",
        "",
        "```",
        f"DA① | ME/Climate history Daegu | {summary.get('stamp')}",
        "```",
        "",
    ]
    (out / "README.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    stamp = datetime.now(KST).strftime("%Y%m%d")
    files = resolve_files()
    if not files:
        raise SystemExit("no xlsx found in Downloads")

    out = REPO / "docs" / "data" / "extracted" / "charger" / "usage" / f"me_history_daegu_{stamp}"
    fig_dir = out / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)

    parts = [load_daegu(p) for p in files]
    raw = pd.concat(parts, ignore_index=True)
    d = enrich(raw)

    # save monthly + all
    d.to_csv(out / "daegu_me_history_all.csv", index=False, encoding="utf-8-sig")
    for m, g in d.groupby("month"):
        g.to_csv(out / f"daegu_me_history_{m}.csv", index=False, encoding="utf-8-sig")

    intens = (
        d.groupby(["station_key", "충전소명", "시군구", "지역"], dropna=False)
        .agg(
            sessions=("충전소명", "size"),
            kwh_sum=("충전량_num", "sum"),
            kwh_mean=("충전량_num", "mean"),
            months=("month", "nunique"),
        )
        .reset_index()
        .sort_values("sessions", ascending=False)
    )
    intens.to_csv(out / "station_intensity.csv", index=False, encoding="utf-8-sig")

    figs = [
        plot_monthly(d, fig_dir),
        plot_hourly(d, fig_dir),
        plot_district(d, fig_dir),
        plot_type(d, fig_dir),
        plot_weekend(d, fig_dir),
    ]

    months = sorted(d["month"].dropna().unique().tolist())
    by_month = d.groupby("month").size()
    summary = {
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "stamp": stamp,
        "n_files": len(files),
        "files": [p.name for p in files],
        "months": months,
        "n_months": len(months),
        "month_min": months[0] if months else None,
        "month_max": months[-1] if months else None,
        "daegu_sessions": int(len(d)),
        "stations": int(d["station_key"].nunique()),
        "kwh_total": float(d["충전량_num"].sum(skipna=True)),
        "kwh_mean": float(d["충전량_num"].mean(skipna=True)),
        "kwh_median": float(d["충전량_num"].median(skipna=True)),
        "min_mean": float(d["충전분"].mean(skipna=True)),
        "sessions_per_month_median": float(by_month.median()) if len(by_month) else 0,
        "top_districts": d["시군구"].value_counts().head(5).to_dict(),
        "top_types": d["충전소 유형(대분류)"].value_counts().head(5).to_dict(),
        "figures": [p.name for p in figs],
    }
    (out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_report(out, summary, figs)

    # team share + desktop
    share = REPO / "docs" / "팀공유" / f"충전이력_대구_{stamp}"
    if share.exists():
        shutil.rmtree(share)
    # copy report essentials (not necessarily full multi-CSV if huge — copy all)
    shutil.copytree(out, share)

    desk = Path.home() / "Desktop" / f"EV_SafeCharge_충전이력_대구_{stamp}"
    if desk.exists():
        shutil.rmtree(desk)
    shutil.copytree(out, desk)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("OUT", out)
    print("DESKTOP", desk)


if __name__ == "__main__":
    main()
