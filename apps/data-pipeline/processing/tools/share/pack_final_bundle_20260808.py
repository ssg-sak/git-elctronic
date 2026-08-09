"""Pack all 20260808 finals into one classified folder under docs/팀공유/.

Does not delete sources. Large folders (>80MB): copy lite artifacts + pointer only.
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[5]
KST = ZoneInfo("Asia/Seoul")
OUT = REPO / "docs" / "팀공유" / "최종본_통합_20260808"
SHARE = REPO / "docs" / "팀공유"
ANALYSIS = REPO / "docs" / "data" / "analysis"
OPS = REPO / "docs" / "data" / "운영"

# section -> list of (src relative to REPO, dest name under section)
PLAN: dict[str, list[tuple[str, str]]] = {
    "00_먼저읽기": [
        ("docs/팀공유/이름_쉬운말_안내_20260808.md", "이름_쉬운말_안내_20260808.md"),
        ("docs/팀공유/최종파일명_확정_20260808.md", "최종파일명_확정_20260808.md"),
        ("docs/팀공유/ETA_동대구고정_한계_조장필독_20260808.md", "ETA_동대구고정_한계_조장필독_20260808.md"),
        ("docs/팀공유/모델적합도_과적합_완료패키지_20260808.md", "모델적합도_과적합_완료패키지_20260808.md"),
        ("docs/팀공유/D1_KPI_핸드오프_20260808.md", "D1_KPI_핸드오프_20260808.md"),
    ],
    "01_현재표_KPI": [
        ("docs/팀공유/D1_최신화의미_20260808", "D1_최신화의미_20260808"),
        ("docs/data/운영/KPI_보고서.md", "KPI_보고서.md"),
        ("docs/data/analysis/d1_explain_20260808", "d1_explain_20260808"),
        ("docs/data/analysis/data_validity_assessment_20260808", "data_validity_assessment_20260808"),
        ("docs/data/analysis/integration_readiness_20260808", "integration_readiness_20260808"),
    ],
    "02_시간표_가용률_수집": [
        ("docs/팀공유/시간대_가용률_20260808", "시간대_가용률_20260808"),
        ("docs/팀공유/상태수집_패널차트_20260808", "상태수집_패널차트_20260808"),
    ],
    "03_혼잡_돌발": [
        ("docs/팀공유/도시혼잡_시계열_20260808", "도시혼잡_시계열_20260808"),
        ("docs/팀공유/돌발_UTIC_분석_20260808", "돌발_UTIC_분석_20260808"),
        ("docs/data/analysis/city_congestion_20260808", "city_congestion_20260808"),
        ("docs/data/analysis/utic_incidents_20260808", "utic_incidents_20260808"),
    ],
    "04_ETA_도착라벨": [
        ("docs/팀공유/ETA_실제_라벨_20260808", "ETA_실제_라벨_20260808"),
        ("docs/data/analysis/station_tmap_eta_20260808", "station_tmap_eta_20260808"),
        ("docs/data/analysis/arrival_labels_tmap_eta_20260808", "arrival_labels_tmap_eta_20260808"),
        ("docs/data/analysis/derived_v0_20260808", "derived_v0_20260808"),
        ("docs/data/analysis/arrival_availability_replay_20260808", "arrival_availability_replay_20260808"),
    ],
    "05_HGB_피처_과적합": [
        ("docs/팀공유/피처선정_최종_HGB_도착ETA_20260808", "피처선정_최종_HGB_도착ETA_20260808"),
        ("docs/팀공유/피처적합도_HGB_도착ETA_20260808", "피처적합도_HGB_도착ETA_20260808"),
        ("docs/팀공유/과적합위험_HGB_도착ETA_20260808", "과적합위험_HGB_도착ETA_20260808"),
        ("docs/data/analysis/hgb_arrival_eta_fitness_20260808", "hgb_arrival_eta_fitness_20260808"),
        ("docs/data/analysis/hgb_overfit_risk_20260808", "hgb_overfit_risk_20260808"),
    ],
    "06_시각화팩": [
        ("docs/팀공유/시각화팩_통합_20260808", "시각화팩_통합_20260808"),
    ],
    "07_EDA": [
        ("docs/팀공유/EDA_최종_20260808", "EDA_최종_20260808"),
    ],
}

LITE_MAX_BYTES = 80 * 1024 * 1024
LITE_KEEP_SUFFIXES = {".md", ".json", ".csv", ".png", ".jpg", ".jpeg", ".webp", ".txt", ".log"}
LITE_FILE_MAX = 2 * 1024 * 1024  # even .csv/.json capped in lite mode
SKIP_NAMES = {".DS_Store", "Thumbs.db"}
SKIP_SUFFIXES_ALWAYS = {".parquet", ".zip", ".pkl", ".joblib"}


def _dir_size(p: Path) -> int:
    if not p.exists():
        return 0
    if p.is_file():
        return p.stat().st_size
    total = 0
    for f in p.rglob("*"):
        if f.is_file():
            total += f.stat().st_size
    return total


def _copy_lite(src: Path, dest: Path) -> dict:
    """Copy md/json/csv/png (+ small files <5MB); write FULL_PATH.txt for rest."""
    dest.mkdir(parents=True, exist_ok=True)
    copied = 0
    skipped = 0
    for f in src.rglob("*"):
        if not f.is_file() or f.name in SKIP_NAMES:
            continue
        rel = f.relative_to(src)
        suf = f.suffix.lower()
        size = f.stat().st_size
        if suf in SKIP_SUFFIXES_ALWAYS or size > LITE_FILE_MAX:
            skipped += 1
            continue
        if suf not in LITE_KEEP_SUFFIXES and size >= LITE_FILE_MAX:
            skipped += 1
            continue
        keep = suf in LITE_KEEP_SUFFIXES or size < LITE_FILE_MAX
        if not keep:
            skipped += 1
            continue
        out = dest / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, out)
        copied += 1
    (dest / "FULL_PATH.txt").write_text(
        "\n".join(
            [
                "# 대용량 — 이 폴더는 요약본만 복사됨",
                f"원본 전체: {src.resolve()}",
                f"복사 파일 수: {copied}",
                f"생략(대용량) 대략: {skipped}+",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return {"mode": "lite", "copied": copied, "skipped_heavy": skipped}


def _copy_full(src: Path, dest: Path) -> dict:
    if dest.exists():
        shutil.rmtree(dest) if dest.is_dir() else dest.unlink()
    if src.is_file():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        return {"mode": "file", "bytes": src.stat().st_size}
    shutil.copytree(src, dest)
    return {"mode": "full", "bytes": _dir_size(dest)}


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    report: dict = {"stamp": "20260808", "sections": {}, "missing": []}

    for section, items in PLAN.items():
        sec_dir = OUT / section
        sec_dir.mkdir(parents=True, exist_ok=True)
        sec_meta = []
        for rel, name in items:
            src = REPO / rel
            dest = sec_dir / name
            if not src.exists():
                report["missing"].append(rel)
                continue
            size = _dir_size(src)
            if src.is_dir() and size > LITE_MAX_BYTES:
                meta = _copy_lite(src, dest)
            else:
                meta = _copy_full(src, dest)
            meta.update({"src": rel, "dest": f"{section}/{name}", "src_bytes": size})
            sec_meta.append(meta)
        report["sections"][section] = sec_meta

    # README
    lines = [
        "# 최종본 통합 — 2026-08-08",
        "",
        "> DA① 0808 **최종본만** 분류해 모은 폴더. 원본은 `docs/팀공유/`, `docs/data/analysis/` 에 그대로 둠.",
        f"> 생성: {datetime.now(KST).isoformat(timespec='seconds')}",
        "",
        "## 폴더 안내",
        "",
        "| 폴더 | 내용 |",
        "|---|---|",
        "| `00_먼저읽기/` | 이름·파일명·동대구 ETA 한계·적합도 한 장·KPI 핸드오프 |",
        "| `01_현재표_KPI/` | 현재표 의미·KPI 보고서·타당성·연동준비 |",
        "| `02_시간표_가용률_수집/` | 시간대 가용률·상태수집 패널 차트 |",
        "| `03_혼잡_돌발/` | 도시 혼잡·UTIC |",
        "| `04_ETA_도착라벨/` | TMAP ETA·도착라벨·derived·replay(대용량은 요약) |",
        "| `05_HGB_피처_과적합/` | 피처선정·적합도·과적합 |",
        "| `06_시각화팩/` | 통합 시각화 팩 복사본 |",
        "| `07_EDA/` | EDA 최종본 (E1~E5·그림) |",
        "",
        "## 말하는 이름",
        "",
        "- **현재표** = 예전 D1",
        "- **시간표** = 예전 D2",
        "",
        "자세한 말 → `00_먼저읽기/이름_쉬운말_안내_20260808.md`",
        "",
        "## 주의",
        "",
        "- `04_ETA_도착라벨/arrival_availability_replay_20260808/` 는 원본 ~388MB → **요약+FULL_PATH.txt**",
        "- 점수·추천 순위 없음 (② 영역)",
        "- 8/9 재생성 후 stamp를 `20260809`로 바꿔 같은 구조로 다시 묶으면 됨",
        "",
        "```",
        "DA① | final bundle 20260808",
        "```",
        "",
    ]
    (OUT / "README.md").write_text("\n".join(lines), encoding="utf-8")
    (OUT / "pack_meta.json").write_text(
        json.dumps(
            {
                **report,
                "out": str(OUT.relative_to(REPO)).replace("\\", "/"),
                "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    n_ok = sum(len(v) for v in report["sections"].values())
    print(
        json.dumps(
            {
                "ok": True,
                "out": str(OUT),
                "items": n_ok,
                "missing": report["missing"],
                "bytes": _dir_size(OUT),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
