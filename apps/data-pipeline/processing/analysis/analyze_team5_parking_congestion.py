"""EDA for Team5 PIS parking realtime history exported from MySQL.

Reads the latest local full snapshot; does not contact Team5 DB.

Usage (repo root):
  python apps/data-pipeline/processing/analysis/analyze_team5_parking_congestion.py
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib.pyplot as plt
import pandas as pd

import sys

_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))
from _bootstrap import ensure_paths

REPO = ensure_paths()
from loop_paths import EXTRACTED_PARKING  # noqa: E402

KST = ZoneInfo("Asia/Seoul")
plt.rcParams["font.family"] = ["Malgun Gothic", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def _style(ax) -> None:
    ax.set_facecolor("#ffffff")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.25)


def source_csv() -> Path:
    hits = sorted(EXTRACTED_PARKING.glob("team5_full_snapshot_*/parking_realtime_status.csv"))
    if not hits:
        raise FileNotFoundError("Run export_team5_parking_snapshot.py first.")
    return hits[-1]


def incremental_csvs() -> list[Path]:
    return sorted(
        EXTRACTED_PARKING.glob(
            "incremental/*/team5_parking_incremental_*/parking_realtime_status_new.csv"
        )
    )


def load(path: Path) -> pd.DataFrame:
    frames = [pd.read_csv(path)]
    frames.extend(
        pd.read_csv(incremental)
        for incremental in incremental_csvs()
        if incremental.stat().st_size > 3
    )
    d = pd.concat(frames, ignore_index=True)
    if "id" in d.columns:
        d = d.drop_duplicates("id", keep="last")
    d["collected_at"] = pd.to_datetime(d["collected_at"], errors="coerce")
    d["occupancy_rate"] = pd.to_numeric(d["occupancy_rate"], errors="coerce")
    d["remaining_spaces"] = pd.to_numeric(d["remaining_spaces"], errors="coerce")
    d["total_spaces"] = pd.to_numeric(d["total_spaces"], errors="coerce")
    d = d.dropna(subset=["pklt_id", "collected_at"]).copy()
    d["hour"] = d["collected_at"].dt.hour
    d["date"] = d["collected_at"].dt.date.astype(str)
    return d


def plot_fleet_ts(batch: pd.DataFrame, fig_dir: Path) -> Path:
    fig, ax = plt.subplots(figsize=(12, 4.5), facecolor="#f7f8fa")
    _style(ax)
    ax.plot(batch["collected_at"], batch["occ_mean"], color="#e45756", label="평균 점유율")
    ax.plot(batch["collected_at"], batch["occ_median"], color="#4c78a8", label="중앙 점유율")
    ax.set_title("주차 realtime 배치별 점유율", loc="left", fontweight="bold")
    ax.set_xlabel("수집 시각 (KST)")
    ax.set_ylabel("점유율 (%)")
    ax.legend(frameon=False)
    out = fig_dir / "01_fleet_occupancy_timeseries.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_hourly(hourly: pd.DataFrame, fig_dir: Path) -> Path:
    fig, ax = plt.subplots(figsize=(11, 4.4), facecolor="#f7f8fa")
    _style(ax)
    ax.bar(hourly["hour"], hourly["occupancy_rate_mean"], color="#f58518")
    ax.set_xticks(range(24))
    ax.set_title("시간대별 평균 점유율", loc="left", fontweight="bold")
    ax.set_xlabel("시 (KST)")
    ax.set_ylabel("평균 점유율 (%)")
    out = fig_dir / "02_hourly_occupancy.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_congestion_share(batch: pd.DataFrame, fig_dir: Path) -> Path:
    labels = [
        "여유(점유 50%미만)",
        "보통(점유 70%미만)",
        "혼잡(점유 90%미만)",
        "만차(점유 90%초과)",
    ]
    colors = ["#54a24b", "#f2cf5b", "#f58518", "#e45756"]
    fig, ax = plt.subplots(figsize=(12, 4.5), facecolor="#f7f8fa")
    ax.set_facecolor("#ffffff")
    base = pd.Series(0.0, index=batch.index)
    for label, color in zip(labels, colors, strict=True):
        values = batch.get(label, pd.Series(0.0, index=batch.index))
        ax.fill_between(
            batch["collected_at"],
            base,
            base + values,
            label=label,
            color=color,
            alpha=0.9,
        )
        base = base + values
    ax.set_title("배치별 주차 혼잡 등급 구성", loc="left", fontweight="bold")
    ax.set_xlabel("수집 시각 (KST)")
    ax.set_ylabel("주차장 비율 (%)")
    ax.set_ylim(0, 100)
    ax.legend(frameon=False, ncol=2, loc="upper left")
    out = fig_dir / "03_congestion_mix_timeseries.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_top_lots(lots: pd.DataFrame, fig_dir: Path) -> Path:
    top = lots.sort_values(["occupancy_rate_mean", "observations"], ascending=False).head(15)
    fig, ax = plt.subplots(figsize=(10, 6), facecolor="#f7f8fa")
    _style(ax)
    ax.barh(top["pklt_id"].astype(str).iloc[::-1], top["occupancy_rate_mean"].iloc[::-1], color="#e45756")
    ax.set_title("평균 점유율 상위 주차장 Top15", loc="left", fontweight="bold")
    ax.set_xlabel("평균 점유율 (%)")
    ax.set_ylabel("주차장 ID")
    out = fig_dir / "04_top_congested_lots.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_remaining(d: pd.DataFrame, fig_dir: Path) -> Path:
    clean = d.dropna(subset=["remaining_spaces", "occupancy_rate"]).copy()
    fig, ax = plt.subplots(figsize=(8, 5), facecolor="#f7f8fa")
    _style(ax)
    ax.scatter(
        clean["occupancy_rate"],
        clean["remaining_spaces"],
        s=7,
        alpha=0.18,
        color="#4c78a8",
    )
    ax.set_title("점유율과 잔여면 관계", loc="left", fontweight="bold")
    ax.set_xlabel("점유율 (%)")
    ax.set_ylabel("잔여 주차면 (면)")
    out = fig_dir / "05_occupancy_vs_remaining.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


def write_report(out: Path, s: dict, figs: list[Path]) -> None:
    hourly_lines = "\n".join(
        f"| {int(r.hour):02d}시 | {int(r.batches):,} | {r.occupancy_rate_mean:.1f}% |"
        for r in s["hourly"].itertuples()
    )
    top_lines = "\n".join(
        f"| {i + 1} | {r.pklt_id} | {int(r.observations):,} | {r.occupancy_rate_mean:.1f}% | {r.remaining_spaces_mean:.1f} |"
        for i, r in enumerate(s["lot_profiles"].head(15).itertuples())
    )
    fig_md = "\n".join(
        f"### {path.name}\n\n![{path.name}](figures/{path.name})\n"
        for path in figs
    )
    text = f"""# Team5 PIS 주차 realtime — 초기 혼잡 EDA

| | |
|---|---|
| **생성** | {s['generated_at']} |
| **원천** | `{s['source']}` |
| **범위** | {s['first_at']} ~ {s['last_at']} |
| **단위** | Team5 DB가 적재한 10분 배치 |
| **해석 단계** | **초기 패턴** — {s['dates_n']}개 날짜, 장기 ‘평소’ 판단 금지 |

---

## 1. 요약

- realtime 행: **{s['rows']:,}**
- 주차장: **{s['lots']:,}**
- 수집 배치: **{s['batches']:,}**
- 전체 평균 점유율: **{s['occupancy_mean']:.1f}%**
- 전체 중앙 점유율: **{s['occupancy_median']:.1f}%**
- 만차 상태 행 비율: **{s['full_share']:.1f}%**

현재 이력은 7/23 일부 + 7/24 + 7/25 일부다. 주말·평일과 시간대가 충분히 반복되지 않았으므로,
“평소 자주 혼잡한 주차장” 확정값이 아니라 **추가 수집 전 초기 관찰값**으로만 쓴다.

---

## 2. 시간대별 초기 패턴

| 시간 | 배치 수 | 평균 점유율 |
|---|---:|---:|
{hourly_lines}

---

## 3. 평균 점유율 상위 주차장

| 순위 | 주차장 ID | 관측 수 | 평균 점유율 | 평균 잔여면 |
|---:|---|---:|---:|---:|
{top_lines}

> 주차장 이름·주소는 `parking_lot_info.csv`의 `pklt_id`로 연결한다.

---

## 4. SafeCharge 활용 범위

| 가능 | 아직 금지 |
|---|---|
| 최신 배치의 잔여면·점유율을 D1 보조 정보로 사용 | 2.5일 이력으로 장기 혼잡도 점수 확정 |
| 2주 이상 쌓인 뒤 주차장×요일×시간 프로파일 생성 | 주차 혼잡만으로 추천 순위 결정 |
| 충전소↔주차장 1km 조인 품질 점검 | Team5 소유 DB를 합의 없이 지속 복제 |

권장 누적 방식: Team5 DB가 보관한 새 realtime 행만 **주기적 incremental export**한다.
10분마다 별도 원천 호출을 만들 필요는 없고, DB 보관·접근 정책은 Team5와 합의한다.

---

## 5. 그림

{fig_md}

```
DA① | Team5 PIS parking EDA | 20260725
```
"""
    (out / "README.md").write_text(text, encoding="utf-8")


def main() -> int:
    path = source_csv()
    d = load(path)
    if d.empty:
        raise SystemExit("empty parking history")

    stamp = datetime.now(KST).strftime("%Y%m%d")
    out = REPO / "docs" / "data" / "analysis" / f"team5_parking_eda_{stamp}"
    fig_dir = out / "figures"
    if out.exists():
        shutil.rmtree(out)
    fig_dir.mkdir(parents=True)

    batch_occ = (
        d.groupby("collected_at", as_index=False)
        .agg(
            occ_mean=("occupancy_rate", "mean"),
            occ_median=("occupancy_rate", "median"),
            lots=("pklt_id", "nunique"),
        )
    )
    mix = (
        d.dropna(subset=["congestion_status"])
        .groupby(["collected_at", "congestion_status"])
        .size()
        .unstack(fill_value=0)
    )
    mix = mix.div(mix.sum(axis=1), axis=0).mul(100).reset_index()
    batch = batch_occ.merge(mix, on="collected_at", how="left")

    hourly = (
        d.groupby("hour", as_index=False)
        .agg(
            batches=("collected_at", "nunique"),
            occupancy_rate_mean=("occupancy_rate", "mean"),
            remaining_spaces_mean=("remaining_spaces", "mean"),
        )
        .sort_values("hour")
    )
    lots = (
        d.groupby("pklt_id", as_index=False)
        .agg(
            observations=("id", "size"),
            occupancy_rate_mean=("occupancy_rate", "mean"),
            occupancy_rate_median=("occupancy_rate", "median"),
            remaining_spaces_mean=("remaining_spaces", "mean"),
        )
        .sort_values(["occupancy_rate_mean", "observations"], ascending=False)
    )

    batch.to_csv(out / "batch_summary.csv", index=False, encoding="utf-8-sig")
    hourly.to_csv(out / "hourly_profile.csv", index=False, encoding="utf-8-sig")
    lots.to_csv(out / "lot_profile.csv", index=False, encoding="utf-8-sig")
    d.to_csv(out / "parking_realtime_history_used.csv", index=False, encoding="utf-8-sig")

    figs = [
        plot_fleet_ts(batch, fig_dir),
        plot_hourly(hourly, fig_dir),
        plot_congestion_share(batch, fig_dir),
        plot_top_lots(lots, fig_dir),
        plot_remaining(d, fig_dir),
    ]
    full_count = int(d["congestion_status"].eq("만차(점유 90%초과)").sum())
    s = {
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "source": str(path.relative_to(REPO)).replace("\\", "/"),
        "incremental_sources": [
            str(incremental.relative_to(REPO)).replace("\\", "/")
            for incremental in incremental_csvs()
        ],
        "first_at": str(d["collected_at"].min()),
        "last_at": str(d["collected_at"].max()),
        "rows": int(len(d)),
        "lots": int(d["pklt_id"].nunique()),
        "batches": int(d["collected_at"].nunique()),
        "dates_n": int(d["date"].nunique()),
        "occupancy_mean": float(d["occupancy_rate"].mean()),
        "occupancy_median": float(d["occupancy_rate"].median()),
        "full_share": float(full_count / len(d) * 100),
        "figures": [path.name for path in figs],
    }
    (out / "summary.json").write_text(
        json.dumps(s, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_report(out, {**s, "hourly": hourly, "lot_profiles": lots}, figs)

    share = REPO / "docs" / "팀공유" / f"주차_혼잡_EDA_{stamp}"
    if share.exists():
        shutil.rmtree(share)
    shutil.copytree(out, share)
    desktop = Path.home() / "Desktop" / f"EV_SafeCharge_주차_혼잡_EDA_{stamp}"
    if desktop.exists():
        shutil.rmtree(desktop)
    shutil.copytree(out, desktop)

    print(json.dumps(s, ensure_ascii=False, indent=2))
    print("OUT", out)
    print("DESKTOP", desktop)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
