"""Explain + visualize latest D1 snapshot for team handoff.

Usage (repo root):
  python apps/data-pipeline/processing/analysis/explain_d1_latest.py
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

plt.rcParams["font.family"] = ["Malgun Gothic", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

D1_PATH = (
    REPO
    / "apps/data-pipeline/evaluation/results/datasets/station_feature_snapshot_latest.csv"
)
KPI_JSON = REPO / "apps/data-pipeline/evaluation/results/kpi_report_latest.json"


def _bool(s: pd.Series) -> pd.Series:
    return s.astype(str).str.lower().isin(["true", "1", "yes"])


def load() -> tuple[pd.DataFrame, dict]:
    d1 = pd.read_csv(D1_PATH, low_memory=False)
    kpi = {}
    if KPI_JSON.exists():
        kpi = json.loads(KPI_JSON.read_text(encoding="utf-8"))
    return d1, kpi


def plot_public_split(d1: pd.DataFrame, fig_dir: Path) -> Path:
    pub = int(_bool(d1["recommend_public_default"]).sum())
    rest = len(d1) - pub
    fig, ax = plt.subplots(figsize=(8.5, 4.8), facecolor="#f7f8fa")
    ax.set_facecolor("#ffffff")
    bars = ax.bar(
        ["공용 후보\n(recommend_public_default)", "이용제한\n(access_restricted)"],
        [pub, rest],
        color=["#18794e", "#9e9e9e"],
        width=0.55,
    )
    ax.set_ylabel("충전소 수")
    ax.set_title("D1 충전소 풀 나누기 (limitYn 기준)", loc="left", fontweight="bold")
    for b, v in zip(bars, [pub, rest]):
        ax.text(b.get_x() + b.get_width() / 2, v + 40, f"{v:,}\n({100*v/len(d1):.1f}%)", ha="center", fontsize=11)
    ax.set_ylim(0, max(pub, rest) * 1.25)
    ax.spines[["top", "right"]].set_visible(False)
    ax.text(
        0.02,
        -0.18,
        "추천 기본 풀은 왼쪽(공용). 오른쪽을 지우지 않음 — 플래그만 둠.",
        transform=ax.transAxes,
        fontsize=9,
        color="#555",
    )
    out = fig_dir / "01_public_vs_restricted.png"
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_public_availability(d1: pd.DataFrame, fig_dir: Path) -> Path:
    pub = d1[_bool(d1["recommend_public_default"])].copy()
    conf = int(_bool(pub["has_confirmed_available"]).sum())
    no = len(pub) - conf
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6), facecolor="#f7f8fa")
    for ax in axes:
        ax.set_facecolor("#ffffff")
        ax.spines[["top", "right"]].set_visible(False)

    axes[0].bar(["확정 가용\n(has_confirmed_available)", "그 외"], [conf, no], color=["#4c78a8", "#c8cdd3"])
    axes[0].set_title(f"공용 {len(pub):,}곳 중 확정 가용", loc="left", fontweight="bold")
    axes[0].set_ylabel("충전소 수")
    axes[0].text(0, conf + 20, f"{conf:,}\n({100*conf/len(pub):.1f}%)", ha="center")

    ratio = pd.to_numeric(pub["availability_ratio_observed"], errors="coerce").dropna()
    axes[1].hist(ratio, bins=20, color="#54a24b", edgecolor="white")
    axes[1].axvline(ratio.mean(), color="#222", ls="--", lw=1.5, label=f"평균 {ratio.mean():.2f}")
    axes[1].set_title("공용 · 관측 가용률 분포", loc="left", fontweight="bold")
    axes[1].set_xlabel("availability_ratio_observed")
    axes[1].legend(frameon=False)
    axes[1].text(
        0.02,
        -0.2,
        "미관측 충전기는 분모에서 뺌. 0으로 채우지 않음.",
        transform=axes[1].transAxes,
        fontsize=8.5,
        color="#555",
    )
    out = fig_dir / "02_public_availability.png"
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_usage(d1: pd.DataFrame, fig_dir: Path) -> Path:
    pub = d1[_bool(d1["recommend_public_default"])].copy()
    hist = _bool(d1["history_observed"]) if "history_observed" in d1.columns else d1["usage_level"].notna()
    levels = pub.loc[pub["usage_level"].astype(str).str.strip().isin(["적음", "보통", "많음"]), "usage_level"]
    order = ["적음", "보통", "많음"]
    counts = [int((levels == x).sum()) for x in order]

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6), facecolor="#f7f8fa")
    for ax in axes:
        ax.set_facecolor("#ffffff")
        ax.spines[["top", "right"]].set_visible(False)

    covered = int(hist.sum())
    axes[0].bar(["이용강도 있음", "없음(null)"], [covered, len(d1) - covered], color=["#f58518", "#e0e0e0"])
    axes[0].set_title("전체 D1 · 이용강도 커버", loc="left", fontweight="bold")
    axes[0].text(0, covered + 30, f"{covered}", ha="center")

    axes[1].bar(order, counts, color=["#54a24b", "#f58518", "#e45756"])
    axes[1].set_title("공용 후보 · usage_level", loc="left", fontweight="bold")
    axes[1].set_ylabel("충전소 수")
    for i, v in enumerate(counts):
        axes[1].text(i, v + 1, str(v), ha="center")
    axes[1].text(
        0.02,
        -0.2,
        "과거 이용 보조 신호. 실시간 가용을 덮어쓰지 않음.",
        transform=axes[1].transAxes,
        fontsize=8.5,
        color="#555",
    )
    out = fig_dir / "03_usage_level.png"
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_parking_traffic(d1: pd.DataFrame, fig_dir: Path) -> Path:
    park_m = pd.to_numeric(d1.get("nearest_parking_m"), errors="coerce")
    park_hit = int(park_m.notna().sum())
    inc = pd.to_numeric(d1.get("nearest_incident_m"), errors="coerce")
    inc_hit = int(inc.notna().sum()) if inc is not None else 0

    fig, ax = plt.subplots(figsize=(8.5, 4.8), facecolor="#f7f8fa")
    ax.set_facecolor("#ffffff")
    labels = ["주차 1km 매칭\n(team5_pis)", "돌발 1km 매칭\n(UTIC)"]
    vals = [park_hit, inc_hit]
    bars = ax.bar(labels, vals, color=["#4c78a8", "#b279a2"], width=0.5)
    ax.set_ylabel("매칭된 충전소 수")
    ax.set_title("공간 보조 피처 커버 (D1)", loc="left", fontweight="bold")
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 30, f"{v:,}\n({100*v/len(d1):.1f}%)", ha="center")
    ax.set_ylim(0, max(vals) * 1.3)
    ax.spines[["top", "right"]].set_visible(False)
    src = d1["parking_source"].iloc[0] if "parking_source" in d1.columns else "?"
    ax.text(
        0.02,
        -0.18,
        f"parking_source={src} · mock 거리 미투입. 미매칭은 null.",
        transform=ax.transAxes,
        fontsize=9,
        color="#555",
    )
    out = fig_dir / "04_parking_incident_coverage.png"
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return out


def write_doc(out_dir: Path, d1: pd.DataFrame, kpi: dict, figs: list[Path]) -> None:
    as_of = str(d1["as_of_ts"].iloc[0])
    pub = int(_bool(d1["recommend_public_default"]).sum())
    rest = len(d1) - pub
    conf_all = int(_bool(d1["has_confirmed_available"]).sum())
    pub_df = d1[_bool(d1["recommend_public_default"])]
    conf_pub = int(_bool(pub_df["has_confirmed_available"]).sum())
    d1k = kpi.get("d1", {})

    lines = [
        "# D1 최신화가 의미하는 것 (쉬운 설명 + 그림)",
        "",
        "| | |",
        "|---|---|",
        f"| **기준시각 as_of** | `{as_of}` |",
        f"| **파일** | `station_feature_snapshot_latest.csv` |",
        f"| **행** | 충전소 **{len(d1):,}**곳 (1소=1행) |",
        "| **점수** | 없음 → ②가 읽어서 씀 |",
        "",
        "---",
        "",
        "## 한 줄",
        "",
        "> **지금 이 시각 기준**으로, 대구 충전소마다 “갈 만한지 보는 요약 카드”를 다시 뽑아 둔 것.",
        "> 카드 안에는 **공용/제한**, **지금 비었나**, **예전에 얼마나 썼나**, **근처 주차·돌발**이 같이 적혀 있다.",
        "",
        "---",
        "",
        "## 숫자 해석 (이번 빌드)",
        "",
        "| 숫자 | 뜻 | 이번 값 |",
        "|---|---|---|",
        f"| 전체 소 | D1 행 수 | **{len(d1):,}** |",
        f"| 공용 후보 | `recommend_public_default=true` (limitYn 전부 N) | **{pub:,}** |",
        f"| 이용제한 | `access_restricted=true` (충전기 중 limitYn=Y 하나라도) | **{rest:,}** |",
        f"| 공용 확정 가용 | 공용 중 `has_confirmed_available` | **{conf_pub:,}** ({100*conf_pub/pub:.1f}%) |",
        f"| 공용 관측 가용률 평균 | 관측된 충전기만 분모 | **{d1k.get('public_availability_ratio_observed')}** |",
        f"| 이용강도 붙은 소 | `history_observed` / usage_level | **{d1k.get('usage_level_coverage_n', 200)}** |",
        f"| 주차 1km 매칭 | team5 PIS | **{int(pd.to_numeric(d1['nearest_parking_m'], errors='coerce').notna().sum()):,}** |",
        f"| 돌발 1km 매칭 | UTIC | **{int(pd.to_numeric(d1.get('nearest_incident_m'), errors='coerce').notna().sum()):,}** |",
        "",
        "---",
        "",
        "## 그림",
        "",
    ]
    captions = {
        "01_public_vs_restricted.png": "공용 vs 이용제한 — 추천은 왼쪽 풀",
        "02_public_availability.png": "공용만 본 확정 가용 · 관측 가용률",
        "03_usage_level.png": "과거 이용강도 (보조 · 실시간 덮어쓰기 금지)",
        "04_parking_incident_coverage.png": "주차·돌발 공간 매칭 커버",
    }
    for p in figs:
        cap = captions.get(p.name, p.name)
        lines += [f"### {p.name}", "", f"![{cap}](figures/{p.name})", "", f">{cap}**", ""]

    lines += [
        "---",
        "",
        "## 쉬운 비유",
        "",
        "| D1 말 | 식당으로 치면 |",
        "|---|---|",
        "| as_of | 메뉴판을 찍은 **시각** |",
        "| 공용 후보 | 아무나 들어갈 수 있는 집 |",
        "| 이용제한 | 회원·거주자만 |",
        "| 확정 가용 | “지금 빈자리 있다”고 **확인됨** |",
        "| 관측 가용률 | 확인된 좌석 중 빈 비율 |",
        "| usage_level | 예전에 손님이 많았는지 (적음/보통/많음) |",
        "| nearest_parking_m | 근처 주차장까지 거리 |",
        "| nearest_incident_m | 근처 사고·공사까지 거리 |",
        "",
        "---",
        "",
        "## ②에게 넘길 때",
        "",
        "```text",
        f"D1 latest as_of={as_of}",
        "기본 추천 풀: recommend_public_default=true (약 1853)",
        "usage_level은 보조 신호 (실시간 가용 덮어쓰기 금지)",
        "parking_source=team5_pis · traffic_source=utic",
        "```",
        "",
        "## 다시 뽑기",
        "",
        "```bash",
        "python apps/data-pipeline/processing/analysis/explain_d1_latest.py",
        "# D1 자체 재빌드: docs/data/가이드/D1_최신화_쉬운설명.md 참고",
        "```",
        "",
        "```",
        f"DA① | D1 explain | {datetime.now(KST).strftime('%Y-%m-%d')}",
        "```",
        "",
    ]
    (out_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    d1, kpi = load()
    stamp = datetime.now(KST).strftime("%Y%m%d")
    out = REPO / "docs" / "팀공유" / f"D1_최신화의미_{stamp}"
    fig_dir = out / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)

    figs = [
        plot_public_split(d1, fig_dir),
        plot_public_availability(d1, fig_dir),
        plot_usage(d1, fig_dir),
        plot_parking_traffic(d1, fig_dir),
    ]
    write_doc(out, d1, kpi, figs)

    # also under analysis
    analysis = REPO / "docs" / "data" / "analysis" / f"d1_explain_{stamp}"
    if analysis.exists():
        shutil.rmtree(analysis)
    shutil.copytree(out, analysis)

    # desktop
    desk = Path.home() / "Desktop" / f"EV_SafeCharge_D1_최신화의미_{stamp}"
    if desk.exists():
        shutil.rmtree(desk)
    shutil.copytree(out, desk)

    # tip in 팀공유 README
    team = REPO / "docs" / "팀공유" / "README.md"
    if team.exists():
        text = team.read_text(encoding="utf-8")
        marker = f"D1_최신화의미_{stamp}"
        if marker not in text:
            row = (
                f"| **[`D1_최신화의미_{stamp}/`](./D1_최신화의미_{stamp}/)** "
                f"| D1 숫자가 뭔 뜻인지 + 그림 | 전원 · 특히 ② |\n"
            )
            if "| **[`도시혼잡_" in text:
                text = text.replace("| **[`도시혼잡_", row + "| **[`도시혼잡_", 1)
            elif "| **[`시간대_가용률_" in text:
                text = text.replace("| **[`시간대_가용률_", row + "| **[`시간대_가용률_", 1)
            else:
                text += "\n" + row
            team.write_text(text, encoding="utf-8")

    print(json.dumps({"out": str(out), "desktop": str(desk), "figs": [p.name for p in figs]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
