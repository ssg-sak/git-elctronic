"""Inject freshly run 20260809 checks into repo-root 최종본_20260809/."""
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[5]
OUT = REPO / "최종본_20260809"
SHARE = REPO / "docs" / "팀공유"
ANALYSIS = REPO / "docs" / "data" / "analysis"
QUALITY = REPO / "docs" / "data" / "quality"
EDA_RES = REPO / "apps" / "data-pipeline" / "evaluation" / "results" / "eda"
OPS = REPO / "docs" / "data" / "운영"
KST = ZoneInfo("Asia/Seoul")


def _cp_tree(src: Path, dest: Path) -> bool:
    if not src.exists():
        return False
    if dest.exists():
        shutil.rmtree(dest)
    if src.is_file():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    else:
        shutil.copytree(src, dest)
    return True


def _cp_file(src: Path, dest: Path) -> bool:
    if not src.is_file():
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return True


def _latest(parent: Path, prefix: str) -> Path | None:
    if not parent.is_dir():
        return None
    cands = sorted(
        [p for p in parent.iterdir() if p.name.startswith(prefix)],
        key=lambda p: p.name,
    )
    return cands[-1] if cands else None


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    checks = OUT / "07_검사_게이트_최신_20260809"
    if checks.exists():
        shutil.rmtree(checks)
    checks.mkdir(parents=True)

    placed: list[str] = []
    missing: list[str] = []

    items = [
        ("IQR_이상치검사", _latest(SHARE, "IQR_이상치검사_"), _latest(ANALYSIS, "iqr_outlier_scan_")),
        ("data_validity", None, _latest(ANALYSIS, "data_validity_assessment_")),
        ("integration_readiness", None, _latest(ANALYSIS, "integration_readiness_")),
        ("d1_explain", _latest(SHARE, "D1_최신화의미_"), _latest(ANALYSIS, "d1_explain_")),
        ("city_congestion", _latest(SHARE, "도시혼잡_시계열_"), _latest(ANALYSIS, "city_congestion_")),
        ("utic_incidents", _latest(SHARE, "돌발_UTIC_분석_"), _latest(ANALYSIS, "utic_incidents_")),
    ]

    for name, share_p, anal_p in items:
        dest = checks / name
        dest.mkdir(parents=True, exist_ok=True)
        ok = False
        if share_p and _cp_tree(share_p, dest / share_p.name):
            placed.append(f"07/{name}/{share_p.name}")
            ok = True
        if anal_p and _cp_tree(anal_p, dest / anal_p.name):
            placed.append(f"07/{name}/{anal_p.name}")
            ok = True
        if not ok:
            missing.append(name)

    # quality gates
    qdest = checks / "quality_gates"
    qdest.mkdir(parents=True, exist_ok=True)
    for name in (
        "recommendation_input_monitor_latest.json",
        "recommendation_input_quality_latest.json",
        "recommendation_input_monitor_history.jsonl",
    ):
        # monitor may write to quality/; validate may use different names
        src = QUALITY / name
        if not src.is_file():
            alt = REPO / "docs" / "data" / "quality" / name
            src = alt
        if _cp_file(src, qdest / name):
            placed.append(f"07/quality_gates/{name}")
        else:
            missing.append(name)

    # kpi
    kpi_dest = checks / "KPI"
    kpi_dest.mkdir(parents=True, exist_ok=True)
    for src in (
        OPS / "KPI_보고서.md",
        REPO / "apps" / "data-pipeline" / "evaluation" / "results" / "kpi_report_latest.json",
        QUALITY / "kpi_report_latest.json",
    ):
        if src.is_file() and _cp_file(src, kpi_dest / src.name):
            placed.append(f"07/KPI/{src.name}")

    # EDA results raw + team pack
    eda_dest = checks / "EDA"
    eda_dest.mkdir(parents=True, exist_ok=True)
    if EDA_RES.is_dir():
        data_d = eda_dest / "results_eda"
        data_d.mkdir(exist_ok=True)
        for p in EDA_RES.glob("e*"):
            if p.is_file():
                shutil.copy2(p, data_d / p.name)
                placed.append(f"07/EDA/results_eda/{p.name}")
    eda_share = _latest(SHARE, "EDA_최종_")
    if eda_share:
        _cp_tree(eda_share, eda_dest / eda_share.name)
        placed.append(f"07/EDA/{eda_share.name}")

    # also refresh top-level 02_EDA_KPI
    d02 = OUT / "02_EDA_KPI"
    d02.mkdir(exist_ok=True)
    if eda_share:
        _cp_tree(eda_share, d02 / eda_share.name)
    _cp_file(OPS / "KPI_보고서.md", d02 / "KPI_보고서.md")
    _cp_file(
        REPO / "apps" / "data-pipeline" / "evaluation" / "results" / "kpi_report_latest.json",
        d02 / "kpi_report_latest.json",
    )
    for name in ("recommendation_input_monitor_latest.json", "recommendation_input_quality_latest.json"):
        _cp_file(QUALITY / name, d02 / name)

    # IQR also at top for visibility
    iqr = _latest(SHARE, "IQR_이상치검사_")
    if iqr:
        _cp_tree(iqr, OUT / "08_IQR_이상치검사_최신" / iqr.name)

    # checks README
    (checks / "README.md").write_text(
        "\n".join(
            [
                "# 07_검사_게이트_최신_20260809",
                "",
                f"생성: {datetime.now(KST).isoformat(timespec='seconds')}",
                "",
                "오늘(8/9) 재실행한 검사 모음.",
                "",
                "| 하위 | 내용 |",
                "|---|---|",
                "| `IQR_이상치검사/` | IQR 스캔 (현재표 as_of 반영) |",
                "| `data_validity/` | 데이터 타당성 |",
                "| `integration_readiness/` | 연동 준비도 |",
                "| `quality_gates/` | validate · monitor |",
                "| `KPI/` | KPI 보고서 |",
                "| `EDA/` | E1~E5 결과 · EDA 최종 팩 |",
                "| `d1_explain/` · `city_congestion/` · `utic_incidents/` | 설명·혼잡·돌발 |",
                "",
                f"- placed: {len(placed)}",
                f"- missing: {missing if missing else '없음'}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    # update root README pointer
    root_readme = OUT / "README.md"
    if root_readme.is_file():
        text = root_readme.read_text(encoding="utf-8")
        if "07_검사_게이트" not in text:
            text = text.replace(
                "| `06_수집_pull/` | Lightsail pull 메타 |",
                "| `06_수집_pull/` | Lightsail pull 메타 |\n"
                "| `07_검사_게이트_최신_20260809/` | **IQR·타당성·연동·EDA·KPI·게이트 (오늘 재실행)** |\n"
                "| `08_IQR_이상치검사_최신/` | IQR 바로가기 |",
            )
            root_readme.write_text(text, encoding="utf-8")

    meta = {
        "injected_at": datetime.now(KST).isoformat(timespec="seconds"),
        "placed_n": len(placed),
        "placed": placed,
        "missing": missing,
    }
    (checks / "inject_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "placed_n": len(placed), "missing": missing}, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
