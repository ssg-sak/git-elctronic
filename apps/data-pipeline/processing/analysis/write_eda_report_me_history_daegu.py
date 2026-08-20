"""EDA report for cleaned Daegu ME/Climate charging history.

Usage (repo root):
  python apps/data-pipeline/processing/analysis/write_eda_report_me_history_daegu.py
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
REPO = Path(__file__).resolve().parents[4]
SRC = REPO / "docs" / "팀공유" / "충전이력_대구_20260724" / "daegu_me_history_all.csv"

plt.rcParams["font.family"] = ["Malgun Gothic", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

DOW_KR = ["월", "화", "수", "목", "금", "토", "일"]


def _style(ax):
    ax.set_facecolor("#ffffff")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.25)


def load() -> pd.DataFrame:
    d = pd.read_csv(SRC, low_memory=False)
    d["start_ts"] = pd.to_datetime(d["start_ts"], errors="coerce")
    d["end_ts"] = pd.to_datetime(d["충전종료일시"], format="%Y%m%d%H%M%S", errors="coerce")
    if d["end_ts"].isna().mean() > 0.5:
        d["end_ts"] = pd.to_datetime(d["충전종료일시"], errors="coerce")
    d["elapsed_min"] = (d["end_ts"] - d["start_ts"]).dt.total_seconds() / 60.0
    d["dur_gap_min"] = (d["elapsed_min"] - d["충전분"]).abs()
    return d


def plot_monthly(d: pd.DataFrame, fig_dir: Path) -> Path:
    g = (
        d.groupby("month", as_index=False)
        .agg(sessions=("충전소명", "size"), kwh=("충전량_num", "sum"))
        .sort_values("month")
    )
    fig, axes = plt.subplots(2, 1, figsize=(11, 6.2), sharex=True, facecolor="#f7f8fa")
    for ax in axes:
        _style(ax)
    axes[0].bar(g["month"], g["sessions"], color="#4c78a8")
    axes[0].set_ylabel("세션 수")
    axes[0].set_title("월별 충전 세션", loc="left", fontweight="bold")
    axes[1].bar(g["month"], g["kwh"] / 1000.0, color="#54a24b")
    axes[1].set_ylabel("충전량 (MWh)")
    axes[1].set_xlabel("월")
    out = fig_dir / "01_monthly.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_hourly(d: pd.DataFrame, fig_dir: Path) -> Path:
    h = d.groupby("hour").size().reindex(range(24), fill_value=0)
    fig, ax = plt.subplots(figsize=(11, 4.2), facecolor="#f7f8fa")
    _style(ax)
    colors = ["#f58518" if i == int(h.idxmax()) else "#fbb04e" for i in h.index]
    ax.bar(h.index, h.values, color=colors)
    ax.set_xticks(range(24))
    ax.set_xlabel("시 (충전 시작)")
    ax.set_ylabel("세션 수")
    ax.set_title("시간대별 충전 시작 분포", loc="left", fontweight="bold")
    out = fig_dir / "02_hourly.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_heatmap(d: pd.DataFrame, fig_dir: Path) -> Path:
    mat = (
        d.groupby(["dow", "hour"])
        .size()
        .unstack(fill_value=0)
        .reindex(index=range(7), columns=range(24), fill_value=0)
    )
    fig, ax = plt.subplots(figsize=(12, 4.8), facecolor="#f7f8fa")
    im = ax.imshow(mat.values, aspect="auto", cmap="YlOrRd")
    ax.set_yticks(range(7))
    ax.set_yticklabels(DOW_KR)
    ax.set_xticks(range(24))
    ax.set_xlabel("시")
    ax.set_title("요일 × 시간대 세션 히트맵", loc="left", fontweight="bold")
    fig.colorbar(im, ax=ax, fraction=0.02, pad=0.02, label="세션 수")
    out = fig_dir / "03_dow_hour_heatmap.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_district_type(d: pd.DataFrame, fig_dir: Path) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), facecolor="#f7f8fa")
    for ax in axes:
        _style(ax)
    dist = d["시군구"].value_counts()
    axes[0].barh(dist.index[::-1], dist.values[::-1], color="#72b7b2")
    axes[0].set_xlabel("세션 수")
    axes[0].set_title("시군구별 세션", loc="left", fontweight="bold")
    typ = d["충전소 유형(대분류)"].value_counts().head(8)
    axes[1].barh(typ.index[::-1], typ.values[::-1], color="#b279a2")
    axes[1].set_xlabel("세션 수")
    axes[1].set_title("시설유형(대분류) Top8", loc="left", fontweight="bold")
    out = fig_dir / "04_district_type.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_kwh_dur(d: pd.DataFrame, fig_dir: Path) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.4), facecolor="#f7f8fa")
    for ax in axes:
        _style(ax)
    kwh = d["충전량_num"].clip(upper=d["충전량_num"].quantile(0.99))
    axes[0].hist(kwh, bins=40, color="#4c78a8", edgecolor="white")
    axes[0].axvline(d["충전량_num"].median(), color="#e45756", ls="--", label="median")
    axes[0].set_xlabel("kWh")
    axes[0].set_ylabel("세션 수")
    axes[0].set_title("세션당 충전량 (상위 1% clip)", loc="left", fontweight="bold")
    axes[0].legend(frameon=False)
    dur = d["충전분"].clip(upper=120)
    axes[1].hist(dur, bins=40, color="#54a24b", edgecolor="white")
    axes[1].axvline(d["충전분"].median(), color="#e45756", ls="--", label="median")
    axes[1].set_xlabel("분 (기록 충전시간, ≤120분)")
    axes[1].set_title("세션당 기록 충전시간", loc="left", fontweight="bold")
    axes[1].legend(frameon=False)
    out = fig_dir / "05_kwh_duration.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_top_stations(d: pd.DataFrame, fig_dir: Path) -> Path:
    g = d.groupby("충전소명").size().sort_values(ascending=False).head(15)
    fig, ax = plt.subplots(figsize=(10, 5.5), facecolor="#f7f8fa")
    _style(ax)
    ax.barh(g.index[::-1], g.values[::-1], color="#e45756")
    ax.set_xlabel("세션 수")
    ax.set_title("충전소별 세션 Top15", loc="left", fontweight="bold")
    out = fig_dir / "06_top_stations.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_capacity_weekend(d: pd.DataFrame, fig_dir: Path) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.4), facecolor="#f7f8fa")
    for ax in axes:
        _style(ax)
    cap = d["충전기용량(KW)"].astype(str).value_counts().head(8)
    axes[0].barh(cap.index[::-1], cap.values[::-1], color="#f58518")
    axes[0].set_title("충전기 용량 구성", loc="left", fontweight="bold")
    axes[0].set_xlabel("세션 수")
    ww = d.groupby(d["is_weekend"].map({False: "평일", True: "주말"})).size()
    axes[1].bar(ww.index, ww.values, color=["#4c78a8", "#f58518"])
    axes[1].set_ylabel("세션 수")
    axes[1].set_title("평일 vs 주말", loc="left", fontweight="bold")
    out = fig_dir / "07_capacity_weekend.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


def build_summary(d: pd.DataFrame) -> dict:
    gap = d["dur_gap_min"]
    heat = d.groupby(["dow", "hour"]).size()
    peak_dow, peak_hour = heat.idxmax()
    monthly = d.groupby("month").size().sort_index()
    return {
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "source_csv": str(SRC.relative_to(REPO)).replace("\\", "/"),
        "period": f"{d['month'].min()} ~ {d['month'].max()}",
        "n_sessions": int(len(d)),
        "n_stations_name": int(d["충전소명"].nunique()),
        "n_stations_key": int(d["station_key"].nunique()),
        "n_chargers": int(d.groupby(["충전소명", "충전기ID"]).ngroups),
        "kwh_total": float(d["충전량_num"].sum()),
        "kwh_mean": float(d["충전량_num"].mean()),
        "kwh_median": float(d["충전량_num"].median()),
        "min_mean": float(d["충전분"].mean()),
        "min_median": float(d["충전분"].median()),
        "dup_rows": int(d.duplicated().sum()),
        "start_null": int(d["start_ts"].isna().sum()),
        "end_null": int(d["end_ts"].isna().sum()),
        "region_ok": bool((d["지역"] == "대구광역시").all()),
        "addr_ok": bool(d["주소"].astype(str).str.startswith("대구광역시").all()),
        "mismatch_gt5": int((gap > 5).sum()),
        "mismatch_gt5_pct": float((gap > 5).mean() * 100),
        "mismatch_gt60": int((gap > 60).sum()),
        "mismatch_gt60_pct": float((gap > 60).mean() * 100),
        "peak_slot": f"{DOW_KR[int(peak_dow)]} {int(peak_hour)}시",
        "peak_sessions": int(heat.max()),
        "hourly_peak": int(d.groupby("hour").size().idxmax()),
        "monthly": monthly.to_dict(),
        "districts": d["시군구"].value_counts().to_dict(),
        "types": d["충전소 유형(대분류)"].value_counts().to_dict(),
        "top_stations": d.groupby("충전소명").size().sort_values(ascending=False).head(15).to_dict(),
        "charger_types": d["충전기타입"].value_counts().to_dict(),
        "capacity_raw": d["충전기용량(KW)"].astype(str).value_counts().to_dict(),
        "kw_buckets": _kw_buckets(d).to_dict(),
        "slow_sessions": int(
            d["충전기용량(KW)"]
            .astype(str)
            .str.contains(r"완속|7\s*kW|11\s*kW", case=False, na=False)
            .sum()
        ),
        "weekend_share": float(d["is_weekend"].mean()),
    }


def _kw_buckets(d: pd.DataFrame) -> pd.Series:
    def one(s: str) -> str:
        m = re.search(r"(\d+)\s*kW", str(s), re.I)
        if not m:
            return "unknown"
        kw = int(m.group(1))
        if kw <= 50:
            return "50kW"
        if kw <= 100:
            return "100kW"
        if kw <= 200:
            return "200kW"
        if kw <= 350:
            return "350kW"
        return "400kW+"

    return d["충전기용량(KW)"].map(one).value_counts()


def write_report(out: Path, s: dict, figs: list[Path]) -> None:
    monthly_lines = "\n".join(
        f"| {m} | {n:,} |" for m, n in sorted(s["monthly"].items())
    )
    dist_lines = "\n".join(f"| {k} | {v:,} |" for k, v in s["districts"].items())
    type_lines = "\n".join(f"| {k} | {v:,} |" for k, v in list(s["types"].items())[:8])
    top_lines = "\n".join(
        f"| {i+1} | {k} | {v:,} |" for i, (k, v) in enumerate(s["top_stations"].items())
    )
    n = max(s["n_sessions"], 1)
    order = ["50kW", "100kW", "200kW", "350kW", "400kW+", "unknown"]
    buckets = s.get("kw_buckets", {})
    kw_lines = "\n".join(
        f"| {k} | {buckets[k]:,} | {buckets[k] / n * 100:.1f}% |"
        for k in order
        if k in buckets
    )
    fig_block = []
    caps = {
        "01_monthly.png": "월별 세션·충전량",
        "02_hourly.png": "시간대별 시작 분포",
        "03_dow_hour_heatmap.png": "요일×시간 히트맵",
        "04_district_type.png": "시군구·시설유형",
        "05_kwh_duration.png": "충전량·기록시간 분포",
        "06_top_stations.png": "충전소 Top15",
        "07_capacity_weekend.png": "용량·평일/주말",
    }
    for p in figs:
        fig_block += [
            f"### {p.name}",
            "",
            f"![{caps.get(p.name, p.name)}](figures/{p.name})",
            "",
            f"**{caps.get(p.name, p.name)}**",
            "",
        ]
    fig_md = "\n".join(fig_block)

    text = f"""# EDA 보고서 — 대구 공공 충전이력 (Historical Demand)

| | |
|---|---|
| **생성** | {s['generated_at']} |
| **원천** | `{s['source_csv']}` |
| **기간** | {s['period']} (8개월) |
| **필터** | `지역`=대구광역시 AND `주소`가 대구광역시로 시작 |
| **역할** | EV SafeCharge **Historical Demand** (실시간 status / ETA와 분리) |

---

## 1. 한 줄 결론

대구 공용·급속 충전이력 **{s['n_sessions']:,}세션**은 지역 혼입 없이 깨끗하고,  
**오후 2~4시(특히 {s['hourly_peak']}시)·금요일 오후**에 수요가 몰린다.  
세션 수·시간대·소별 강도 EDA에는 **지금 상태 그대로 사용 가능**하다.  
다만 `충전시간`과 (종료−시작) 불일치가 약 **{s['mismatch_gt5_pct']:.2f}%** 있어,  
**점유율(occupancy) 재구성**에는 별도 규칙이 필요하다.

---

## 2. 데이터 개요

| 항목 | 값 |
|---|---:|
| 세션 | **{s['n_sessions']:,}** |
| 충전소(이름) | **{s['n_stations_name']}** |
| 충전소(이름+시군구) | **{s['n_stations_key']}** |
| 충전기(소×충전기ID) | **{s['n_chargers']}** |
| 총 충전량 | **{s['kwh_total']:,.2f} kWh** (~{s['kwh_total']/1000:,.1f} MWh) |
| 세션당 충전량 평균 / 중앙 | {s['kwh_mean']:.2f} / {s['kwh_median']:.2f} kWh |
| 기록 충전시간 평균 / 중앙 | {s['min_mean']:.2f} / {s['min_median']:.2f} 분 |
| 주말 세션 비율 | {s['weekend_share']*100:.1f}% |

### 품질 체크

| 검사 | 결과 |
|---|---:|
| 완전 중복 행 | **{s['dup_rows']}** |
| 시작시각 결측 | **{s['start_null']}** |
| 종료시각 결측 | **{s['end_null']}** |
| 지역 전부 대구광역시 | **{s['region_ok']}** |
| 주소 전부 대구광역시 시작 | **{s['addr_ok']}** |
| \\|기록분 − (종료−시작)\\| > 5분 | **{s['mismatch_gt5']:,}** ({s['mismatch_gt5_pct']:.2f}%) |
| 위 차이 > 60분 | **{s['mismatch_gt60']:,}** ({s['mismatch_gt60_pct']:.2f}%) |

> 전처리에서 타시도·오분류 **7,083건**(광주대구고속도로, 서대구일로, 강진 대구면 등)은 이미 제거됨.

---

## 3. 시간 패턴

### 3.1 월별

| 월 | 세션 |
|---|---:|
{monthly_lines}

- **피크 월:** 2026-01 ({s['monthly'].get('2026-01', 0):,}세션)
- 동절기(12~1월)가 높고, 10·4월이 상대적으로 낮다.

### 3.2 시간대 · 요일

- 시작 시각 피크 시각: **{s['hourly_peak']}시**
- 요일×시간 최다 슬롯: **{s['peak_slot']}** ({s['peak_sessions']:,}세션)
- 패턴: 오전부터 상승 → **14~16시 고점** → 저녁 완만 하락 · 심야 최저
- 요일: **금요일**이 가장 바쁘고, 일요일이 상대적으로 적다

SafeCharge 해석: `도착 예정 시각`이 이 구간에 걸리면 **Busy Risk**를 올리는 근거로 쓸 수 있다  
(실시간 Available과 **곱/가산**하는 보조 신호. 실시간 덮어쓰기 금지).

---

## 4. 공간 · 시설

### 4.1 시군구

| 시군구 | 세션 |
|---|---:|
{dist_lines}

달성·군위 비중이 큰 이유: **고속도로 휴게소(논공·군위 등)** 세션이 큼.  
시내 수요만 보고 싶으면 휴게시설을 분리한 서브셋 EDA가 필요하다.

### 4.2 시설유형 (대분류)

| 유형 | 세션 |
|---|---:|
{type_lines}

### 4.3 충전소 Top15

| 순위 | 충전소 | 세션 |
|---|---|---:|
{top_lines}

---

## 5. 충전량 · 기기 · 출력 버킷

- 충전기타입: 대부분 **DC콤보**
- 세션당 kWh 중앙값 **~{s['kwh_median']:.1f}** — 급속 단기 충전 패턴과 일치
- **완속(slow) 세션: {s.get('slow_sessions', 0)}건** → 본 Historical Demand는 사실상 **급속 전용**

| 명목 출력 버킷 | 세션 | 비율 |
|---|---:|---:|
{kw_lines}

---

## 6. 그림

{fig_md}

---

## 7. SafeCharge에서의 역할

```
실시간 Status  +  Historical Demand(본 데이터)  +  ETA
        │                    │                      │
   지금 Available      시간대·소별 수요 위험         도착시각
        └──────────── Busy Risk / Arrival Availability ──→ Top-N
```

| 지금 쓸 수 있는 것 | 아직 하면 안 되는 것 |
|---|---|
| 월·시간·요일 수요 프로파일 | 이력 kWh로 실시간 available 덮어쓰기 |
| 소별 이용강도 (`station_intensity`) | duration mismatch 행으로 점유율 단정 |
| Busy Risk 보조 피처 | 충전소명만으로 EvCharger `statId` 조인 확정 |

**다음 산출물 후보:** `station_hourly_profile.csv`  
(`station` × `dow` × `hour` → session_count, avg_kwh, avg_duration, demand_score)  
+ EvCharger **statId 매핑** · 관측일수 정규화.

---

## 8. 제품 범위 결정 (추가) — 완속 / kW

팀·리뷰 합의안을 EDA 맥락에 고정한다.

### 8.1 결론

| 정책 | 결정 |
|---|---|
| MVP 추천 대상 | **급속 이상만** (50 / 100 / 200 / 350kW+) |
| 원본·마스터 | **완속도 보존** (삭제 금지) |
| 화면·필터 | 출력 버킷 선택 (전체 급속 · 100↑ · 200↑ · 초급속 등) |
| 엔티티 | **충전소 → 충전기** 유지. 같은 장소를 kW별로 충전소 복제하지 않음 |
| 점수 | kW는 **한 요소**. `effective_power = min(차량최대, 충전기kW)` 후보. 고출력 무조건↑ 금지 |

```text
RAW / CHARGER MASTER
├── slow (보존)
└── fast 50·100·200·350·400 …
          ↓ MVP
Recommendation Candidate = is_fast_charger == True
```

### 8.2 왜 맞나

- SafeCharge 질문 = **“지금 출발 → 도착 시 빨리 충전”** (20~60분). 완속(수시간·주거)은 다른 시나리오.
- 본 13만 세션이 **이미 급속만** → 추천 범위와 Historical Demand가 **일치**.
- 완속을 후보에 넣으면 이력·혼잡 피처가 **급속만 있고 완속은 비대칭**.

### 8.3 발표용 한 줄

> 이동 중 도착시점 충전 가능성을 다루는 서비스로 범위를 정의했고,  
> 확보 이력도 50~400kW 급속이라 추천 후보를 급속으로 한정했다.  
> 급속은 50·100·200·350kW+로 필터하고, 충전소는 하나로 두고 충전기 단위에 출력을 둔다.

상세: `docs/팀공유/팀공유_추천범위_급속_kW_20260724.md`

---

## 9. 재현

```bash
python apps/data-pipeline/processing/analysis/write_eda_report_me_history_daegu.py
```

입력: `docs/팀공유/충전이력_대구_20260724/daegu_me_history_all.csv`

```
DA① | EDA ME/Climate Daegu history | 20260724
```
"""
    (out / "README.md").write_text(text, encoding="utf-8")


def main() -> None:
    if not SRC.exists():
        raise SystemExit(f"missing source: {SRC}")

    stamp = datetime.now(KST).strftime("%Y%m%d")
    out = REPO / "docs" / "팀공유" / f"충전이력_대구_EDA_{stamp}"
    fig_dir = out / "figures"
    if out.exists():
        shutil.rmtree(out)
    fig_dir.mkdir(parents=True, exist_ok=True)

    d = load()
    s = build_summary(d)
    figs = [
        plot_monthly(d, fig_dir),
        plot_hourly(d, fig_dir),
        plot_heatmap(d, fig_dir),
        plot_district_type(d, fig_dir),
        plot_kwh_dur(d, fig_dir),
        plot_top_stations(d, fig_dir),
        plot_capacity_weekend(d, fig_dir),
    ]
    s["figures"] = [p.name for p in figs]
    (out / "eda_summary.json").write_text(
        json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    # light tables for team
    (
        d.groupby("month")
        .agg(sessions=("충전소명", "size"), kwh=("충전량_num", "sum"))
        .reset_index()
        .to_csv(out / "eda_monthly.csv", index=False, encoding="utf-8-sig")
    )
    (
        d.groupby(["dow", "hour"])
        .size()
        .reset_index(name="sessions")
        .to_csv(out / "eda_dow_hour.csv", index=False, encoding="utf-8-sig")
    )
    write_report(out, s, figs)

    desk = Path.home() / "Desktop" / f"EV_SafeCharge_충전이력_대구_EDA_{stamp}"
    if desk.exists():
        shutil.rmtree(desk)
    shutil.copytree(out, desk)

    print(json.dumps({k: s[k] for k in [
        "n_sessions", "n_chargers", "kwh_total", "hourly_peak", "peak_slot",
        "mismatch_gt5", "mismatch_gt5_pct",
    ]}, ensure_ascii=False, indent=2))
    print("OUT", out)
    print("DESKTOP", desk)


if __name__ == "__main__":
    main()
