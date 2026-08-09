"""Build a unified DA① visualization pack + Desktop zip.

Pulls latest team-share / analysis figures (availability, D1, congestion,
UTIC, parking paid-free, feature fitness bars, daily checkpoint) into one folder.
"""
from __future__ import annotations

import json
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

REPO = Path(__file__).resolve().parents[5]
DESK = Path.home() / "Desktop"
KST = ZoneInfo("Asia/Seoul")
SHARE = REPO / "docs" / "팀공유"

# Korean font fallbacks on Windows
plt.rcParams["font.family"] = ["Malgun Gothic", "AppleGothic", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def _latest_dir(prefix: str) -> Path | None:
    cands = sorted(
        [p for p in SHARE.glob(f"{prefix}*") if p.is_dir()],
        key=lambda p: p.stat().st_mtime,
    )
    return cands[-1] if cands else None


def _copy_pngs(src_dir: Path | None, dest: Path, label: str) -> list[str]:
    dest.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    if src_dir is None:
        return copied
    fig_dir = src_dir / "figures" if (src_dir / "figures").is_dir() else src_dir
    for p in sorted(fig_dir.glob("*.png")):
        shutil.copy2(p, dest / p.name)
        copied.append(f"{label}/{p.name}")
    return copied


def _plot_parking_paid_free(out_fig: Path) -> list[str]:
    out_fig.mkdir(parents=True, exist_ok=True)
    csv = SHARE / "주차장요금_추출_20260803" / "주차장_유료무료_간단.csv"
    if not csv.exists():
        csv = REPO / "docs/data/analysis/parking_fee_20260803/주차장_유료무료_간단.csv"
    if not csv.exists():
        return []
    df = pd.read_csv(csv, encoding="utf-8-sig")
    col = "유료무료" if "유료무료" in df.columns else None
    if not col:
        return []
    vc = df[col].fillna("미기재").value_counts()
    # pie
    fig, ax = plt.subplots(figsize=(7, 5), facecolor="#f7f8fa")
    colors = ["#2f6f4e", "#c45c26", "#888888", "#5b7c99"]
    ax.pie(
        vc.values,
        labels=[f"{i}\n{v:,}" for i, v in vc.items()],
        colors=colors[: len(vc)],
        autopct="%1.1f%%",
        startangle=90,
        textprops={"fontsize": 10},
    )
    ax.set_title("주차장 유료/무료 구성 (Team5)", loc="left", fontweight="bold")
    p1 = out_fig / "01_parking_paid_free_pie.png"
    fig.savefig(p1, dpi=160, bbox_inches="tight")
    plt.close(fig)

    # bar
    fig, ax = plt.subplots(figsize=(7, 4), facecolor="#f7f8fa")
    ax.bar(vc.index.astype(str), vc.values, color=colors[: len(vc)])
    ax.set_ylabel("주차장 수")
    ax.set_title("주차장 유료/무료 건수", loc="left", fontweight="bold")
    ax.spines[["top", "right"]].set_visible(False)
    for i, v in enumerate(vc.values):
        ax.text(i, v + max(vc.values) * 0.02, f"{v:,}", ha="center", fontsize=10)
    p2 = out_fig / "02_parking_paid_free_bar.png"
    fig.savefig(p2, dpi=160, bbox_inches="tight")
    plt.close(fig)

    # map scatter if coords
    outs = [p1.name, p2.name]
    if {"lat", "lng"}.issubset(df.columns):
        d = df.copy()
        d["lat"] = pd.to_numeric(d["lat"], errors="coerce")
        d["lng"] = pd.to_numeric(d["lng"], errors="coerce")
        d = d.dropna(subset=["lat", "lng"])
        color_map = {"무료": "#2f6f4e", "유료": "#c45c26", "유료+무료": "#5b7c99", "미기재": "#999999"}
        fig, ax = plt.subplots(figsize=(8, 7), facecolor="#f7f8fa")
        for label, g in d.groupby(d[col].fillna("미기재")):
            ax.scatter(
                g["lng"],
                g["lat"],
                s=12,
                alpha=0.65,
                c=color_map.get(str(label), "#666666"),
                label=f"{label} ({len(g)})",
                edgecolors="none",
            )
        ax.set_xlabel("lng")
        ax.set_ylabel("lat")
        ax.set_title("주차장 유료/무료 지도 분포", loc="left", fontweight="bold")
        ax.legend(frameon=False, fontsize=9)
        ax.set_aspect("equal", adjustable="datalim")
        p3 = out_fig / "03_parking_paid_free_map.png"
        fig.savefig(p3, dpi=160, bbox_inches="tight")
        plt.close(fig)
        outs.append(p3.name)
    return [f"05_주차장_유료무료/{n}" for n in outs]


def _plot_feature_auc(out_fig: Path) -> list[str]:
    out_fig.mkdir(parents=True, exist_ok=True)
    csv = (
        REPO
        / "docs/data/analysis/hgb_training_pipeline_20260803/feature_target_association.csv"
    )
    if not csv.exists():
        return []
    df = pd.read_csv(csv)
    df = df.sort_values("directional_auc", ascending=True)
    fig, ax = plt.subplots(figsize=(8, 7), facecolor="#f7f8fa")
    colors = ["#2f6f4e" if v >= 0.55 else "#c45c26" if v >= 0.52 else "#999999" for v in df["directional_auc"]]
    ax.barh(df["feature"], df["directional_auc"], color=colors)
    ax.axvline(0.55, color="#333333", ls="--", lw=1, label="실용 기준 0.55")
    ax.axvline(0.5, color="#aaaaaa", ls=":", lw=1)
    ax.set_xlabel("directional AUC")
    ax.set_xlim(0.45, 0.9)
    ax.set_title("피처×타겟 변별력 (target_available)", loc="left", fontweight="bold")
    ax.legend(frameon=False, loc="lower right")
    ax.spines[["top", "right"]].set_visible(False)
    p = out_fig / "01_feature_directional_auc.png"
    fig.savefig(p, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return [f"06_피처적합도/{p.name}"]


def main() -> int:
    stamp = datetime.now(KST).strftime("%Y%m%d")
    out = SHARE / f"시각화팩_통합_{stamp}"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    copied: list[str] = []
    sections: list[tuple[str, str, Path | None]] = [
        ("01_시간대_가용률", "시간대_가용률", _latest_dir("시간대_가용률_")),
        ("02_D1_최신화의미", "D1_최신화의미", _latest_dir("D1_최신화의미_")),
        ("03_도시혼잡", "도시혼잡_시계열", _latest_dir("도시혼잡_시계열_")),
        ("04_돌발_UTIC", "돌발_UTIC_분석", _latest_dir("돌발_UTIC_분석_")),
        ("08_상태수집_패널차트", "상태수집_패널차트", _latest_dir("상태수집_패널차트_")),
    ]
    for folder, label, src in sections:
        copied.extend(_copy_pngs(src, out / folder, folder))

    # parking charts (generate)
    copied.extend(_plot_parking_paid_free(out / "05_주차장_유료무료"))
    # feature AUC
    copied.extend(_plot_feature_auc(out / "06_피처적합도"))

    # daily checkpoint png if exists
    cp_root = (
        REPO
        / "apps/data-pipeline/evaluation/personal/results/status_daily"
    )
    day = datetime.now(KST).strftime("%Y-%m-%d")
    cp_dir = cp_root / day
    if not cp_dir.exists():
        days = sorted([p for p in cp_root.iterdir() if p.is_dir()], reverse=True)
        cp_dir = days[0] if days else None
    if cp_dir and cp_dir.exists():
        dest = out / "07_daily_checkpoint"
        dest.mkdir(parents=True, exist_ok=True)
        for p in cp_dir.glob("*.png"):
            shutil.copy2(p, dest / p.name)
            copied.append(f"07_daily_checkpoint/{p.name}")
        for name in ("daily_checkpoint.md", "daily_checkpoint.json"):
            sp = cp_dir / name
            if sp.exists():
                shutil.copy2(sp, dest / name)

    # key docs
    docs_dir = out / "00_가이드"
    docs_dir.mkdir()
    for rel in (
        f"docs/팀공유/D1_KPI_핸드오프_{stamp}.md",
        "docs/팀공유/팀공유_핸드오프_①to②_20260803.md",
        "docs/팀공유/피처적합도_비교_20260803/과적합주의_최적피처_추천.md",
        "docs/팀공유/주차_realtime_428_한계_20260803.md",
        "docs/팀공유/주차장요금_추출_20260803/README.md",
    ):
        src = REPO / rel
        if src.exists():
            shutil.copy2(src, docs_dir / src.name)
            copied.append(f"00_가이드/{src.name}")

    # index README
    by_sec: dict[str, list[str]] = {}
    for item in copied:
        sec = item.split("/")[0]
        by_sec.setdefault(sec, []).append(item.split("/", 1)[-1])

    lines = [
        f"# EV SafeCharge 시각화 팩 (통합 · {stamp})",
        "",
        "| 항목 | 내용 |",
        "|---|---|",
        "| **작성** | AI·데이터 ① |",
        f"| **생성** | {datetime.now(KST).isoformat(timespec='seconds')} |",
        "| **용도** | 팀·조장 공유용 그림 모음 (점수/모델 아님) |",
        "",
        "## 보는 순서",
        "",
        "1. `01_시간대_가용률` — 패널 가용률·히트맵·공용/주거",
        "2. `02_D1_최신화의미` — 공용/제한·주차·돌발 커버",
        "3. `03_도시혼잡` — 소통 혼잡 시계열",
        "4. `04_돌발_UTIC` — 돌발 건수·조인",
        "5. `05_주차장_유료무료` — Team5 유료/무료",
        "6. `06_피처적합도` — target_available 변별력",
        "7. `07_daily_checkpoint` — 당일 수집 health",
        "8. `08_상태수집_패널차트` — 편향/패널·관측분포·데이터가치 공식 차트",
        "9. `00_가이드` — 핸드오프·계약 문서",
        "",
        "## 폴더별 파일",
        "",
    ]
    for sec in sorted(by_sec):
        lines.append(f"### {sec}")
        lines.append("")
        for name in sorted(by_sec[sec]):
            lines.append(f"- `{name}`")
        lines.append("")
    lines += [
        "## 주의",
        "",
        "- 가용률 차트는 **변경분·패널 정의** 기준 — 대구 전체 순간 가용률로 단정 금지",
        "- 주차 realtime≈428 · 유료/무료는 **주차장 마스터** 기준 (~1.7천)",
        "- 피처 AUC는 단변량 — 모델 우승자 선정 ≠ ①",
        "",
        "```",
        f"DA① | viz pack | {stamp}",
        "```",
        "",
    ]
    (out / "README.md").write_text("\n".join(lines), encoding="utf-8")

    meta = {
        "stamp": stamp,
        "out": str(out.relative_to(REPO)).replace("\\", "/"),
        "n_files": len(copied),
        "sections": {k: len(v) for k, v in by_sec.items()},
        "sources": {
            "availability": str(sections[0][2]) if sections[0][2] else None,
            "d1": str(sections[1][2]) if sections[1][2] else None,
            "congestion": str(sections[2][2]) if sections[2][2] else None,
            "utic": str(sections[3][2]) if sections[3][2] else None,
        },
    }
    (out / "pack_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Desktop folder + zip
    desk_name = f"EV_SafeCharge_시각화팩_{stamp}"
    desk_dir = DESK / desk_name
    if desk_dir.exists():
        shutil.rmtree(desk_dir)
    shutil.copytree(out, desk_dir)
    zip_path = DESK / f"{desk_name}.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in desk_dir.rglob("*"):
            if p.is_file():
                zf.write(p, arcname=str(Path(desk_name) / p.relative_to(desk_dir)))

    meta["desktop_folder"] = str(desk_dir)
    meta["desktop_zip"] = str(zip_path)
    meta["zip_bytes"] = zip_path.stat().st_size
    print(json.dumps(meta, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
