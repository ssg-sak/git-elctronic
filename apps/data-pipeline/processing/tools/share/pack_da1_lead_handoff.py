"""Pack DA① → 조장님(DA②) share folder + zip on Desktop.

Includes:
  - handoff docs / contracts
  - model-ready tables (D1, D2, ETA, arrival labels+derived, training, replay)
  - raw collected CSVs
  - DA① reproducible code (processing + key evaluation builders + scripts)
Never packs .env / secrets.
"""
from __future__ import annotations

import json
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[5]
DESK = Path.home() / "Desktop"
KST = ZoneInfo("Asia/Seoul")

IGNORE_DIR_NAMES = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".git",
    "node_modules",
    ".venv",
    "venv",
}
IGNORE_FILE_SUFFIXES = {".pyc", ".pyo"}
IGNORE_FILE_NAMES = {
    ".env",
    ".env.local",
    ".env.loca",
    ".env.example",  # keys sometimes pasted; keep secrets out of zip
}


def _ignore(_dir: str, names: list[str]) -> list[str]:
    skip: list[str] = []
    for n in names:
        if n in IGNORE_DIR_NAMES or n in IGNORE_FILE_NAMES:
            skip.append(n)
            continue
        if any(n.endswith(suf) for suf in IGNORE_FILE_SUFFIXES):
            skip.append(n)
            continue
        if n.startswith(".env"):
            skip.append(n)
    return skip


def _latest_dir(parent: Path, prefix: str) -> Path | None:
    if not parent.is_dir():
        return None
    cands = sorted(
        [p for p in parent.iterdir() if p.is_dir() and p.name.startswith(prefix)],
        key=lambda p: p.name,
    )
    return cands[-1] if cands else None


def main() -> int:
    stamp = datetime.now(KST).strftime("%Y%m%d_%H%M")
    folder_name = f"EV_SafeCharge_DA1to조장_풀데이터_{stamp}"
    out_dir = DESK / folder_name
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    copied: list[str] = []
    missing: list[str] = []

    def copy_file(rel: str, dest_dir: Path, dest_name: str | None = None) -> None:
        src = REPO / rel
        if not src.is_file():
            missing.append(rel)
            return
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest_dir / (dest_name or src.name))
        copied.append(rel)

    def copy_dir(
        rel: str,
        dest_parent: Path,
        dest_name: str | None = None,
        *,
        use_ignore: bool = False,
    ) -> None:
        src = REPO / rel
        if not src.is_dir():
            missing.append(rel)
            return
        target = dest_parent / (dest_name or src.name)
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(src, target, ignore=_ignore if use_ignore else None)
        copied.append(rel + "/")

    def copy_abs_dir(src: Path, dest_parent: Path, dest_name: str) -> None:
        if not src.is_dir():
            missing.append(str(src.relative_to(REPO)).replace("\\", "/"))
            return
        target = dest_parent / dest_name
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(src, target)
        copied.append(str(src.relative_to(REPO)).replace("\\", "/") + "/")

    # --- 00 docs ---
    first = out_dir / "00_먼저읽기"
    for rel in (
        "docs/팀공유/최종패키지_조장전달_목록_20260809.md",
        "docs/팀공유/최종패키지_명령_초안_20260806.md",
        "docs/팀공유/핵심갭_개선계획_20260806.md",
        "docs/팀공유/파생변수_검토_도착라벨_20260806.md",
        "docs/팀공유/팀공유_핸드오프_①to②_20260809.md",
        "docs/팀공유/D1_KPI_핸드오프_20260809.md",
        "docs/팀공유/충전이력_usage_희소성_과적합_20260804.md",
        "docs/팀공유/주차_realtime_428_한계_20260803.md",
        "docs/팀공유/위경도_피처유의성_20260803.md",
        "docs/팀공유/커버리지갭_단계계획_20260731.md",
        "docs/데이터파트_①_8월9일까지_로드맵.md",
        "AGENTS.md",
        "apps/data-pipeline/AGENTS.md",
    ):
        copy_file(rel, first)

    for rel in (
        "docs/팀공유/파생변수_derived_v0_20260806",
        "docs/팀공유/ETA_실제_라벨_20260806",
        "docs/팀공유/ETA_보정샘플_20260806",
    ):
        copy_dir(rel, first)

    # --- 01 fitness ---
    feat = out_dir / "01_피처적합도_유의성"
    feat.mkdir()
    fit = _latest_dir(REPO / "docs/팀공유", "피처적합도_비교_")
    if fit:
        copy_abs_dir(fit, feat, fit.name)
    else:
        missing.append("docs/팀공유/피처적합도_비교_*")
    hgb = _latest_dir(REPO / "docs/data/analysis", "hgb_training_pipeline_")
    if hgb:
        copy_abs_dir(hgb, feat, hgb.name)
    copy_dir("docs/data/analysis/coord_feature_significance_20260803", feat)

    # --- 02 model-ready ---
    data = out_dir / "02_모델테스트_가공본"
    data.mkdir()
    for rel in (
        "apps/data-pipeline/evaluation/results/datasets/station_horizon_training_v1.parquet",
        "apps/data-pipeline/evaluation/results/datasets/station_horizon_training_sample.csv",
        "apps/data-pipeline/evaluation/results/datasets/station_feature_snapshot_latest.csv",
        "apps/data-pipeline/evaluation/results/datasets/station_feature_snapshot_latest.parquet",
        "apps/data-pipeline/evaluation/results/datasets/station_feature_snapshot_with_eta_latest.csv",
        "apps/data-pipeline/evaluation/results/datasets/station_feature_snapshot_with_eta_latest.parquet",
        "apps/data-pipeline/evaluation/results/datasets/station_feature_snapshot_with_eta_derived_latest.csv",
        "apps/data-pipeline/evaluation/results/datasets/station_feature_snapshot_with_eta_derived_latest.parquet",
        "apps/data-pipeline/evaluation/results/datasets/station_tmap_eta_latest.csv",
        "apps/data-pipeline/evaluation/results/datasets/station_tmap_eta_latest.parquet",
        "apps/data-pipeline/evaluation/results/datasets/arrival_labels_tmap_eta_v1.parquet",
        "apps/data-pipeline/evaluation/results/datasets/arrival_labels_tmap_eta_v1_with_derived.parquet",
        "apps/data-pipeline/evaluation/results/datasets/arrival_labels_tmap_eta_v1_with_derived_sample.csv",
        "apps/data-pipeline/evaluation/results/datasets/derived_v0_schema.json",
        "apps/data-pipeline/evaluation/results/datasets/derived_v0_meta.json",
        "apps/data-pipeline/evaluation/results/datasets/station_feature_panel_latest.parquet",
        "apps/data-pipeline/evaluation/results/datasets/station_history_features_latest.csv",
        "apps/data-pipeline/evaluation/results/datasets/station_history_features_meta.json",
        "apps/data-pipeline/evaluation/results/kpi_report_latest.json",
        "apps/data-pipeline/reports/timeseries_feasibility/tables/station_tick_panel.parquet",
    ):
        copy_file(rel, data)
    copy_dir(
        "apps/data-pipeline/evaluation/results/datasets/handoff_to_model",
        data,
    )
    replay = _latest_dir(REPO / "docs/data/analysis", "arrival_availability_replay_")
    if replay:
        copy_abs_dir(replay, data, replay.name)
    else:
        missing.append("docs/data/analysis/arrival_availability_replay_*")

    # --- 03 coverage ---
    cov = out_dir / "03_커버리지_주차"
    cov.mkdir()
    for rel in (
        "docs/팀공유/신축단지_인포대조_20260803",
        "docs/팀공유/인포커버리지갭_20260803",
    ):
        copy_dir(rel, cov)
    copy_file("docs/팀공유/주차_realtime_428_한계_20260803.md", cov)

    # --- 04 RAW ---
    raw = out_dir / "04_원천수집_CSV"
    raw.mkdir()
    copy_dir("docs/data/loops/loop1/snapshots", raw, "loop1_status_snapshots")
    copy_dir("docs/data/loops/loop1/daily", raw, "loop1_status_daily")
    copy_dir("docs/data/loops/loop2", raw, "loop2_utic")
    copy_dir("docs/data/loops/loop3", raw, "loop3_traffic_linkspeed")
    copy_dir("docs/data/extracted/charger/usage", raw, "usage_충전이력")
    copy_dir("docs/data/extracted/daily", raw, "info_일일덤프")
    copy_dir("docs/data/extracted/charger/info", raw, "info_charger")
    copy_dir("docs/data/spatial_join", raw, "spatial_join")
    if (REPO / "docs/data/extracted/parking").is_dir():
        copy_dir("docs/data/extracted/parking", raw, "parking_team5")

    # --- 05 quality ---
    q = out_dir / "05_품질리포트"
    q.mkdir()
    for rel in (
        "docs/data/quality/recommendation_input_monitor_latest.json",
        "docs/data/quality/recommendation_input_quality_latest.json",
    ):
        copy_file(rel, q)
    for prefix in (
        "dedupe_selection_sample_",
        "daily_quality_trend_",
        "horizon_overlap_",
    ):
        parent = REPO / "docs/data/quality"
        cands = sorted(parent.glob(f"{prefix}*.csv")) if parent.is_dir() else []
        if cands:
            rel = str(cands[-1].relative_to(REPO)).replace("\\", "/")
            copy_file(rel, q)
        else:
            missing.append(f"docs/data/quality/{prefix}*.csv")

    # --- 06 CODE (재현·인수인계 핵심) ---
    code = out_dir / "06_재현코드_DA1"
    code.mkdir()
    for rel, dest_name in (
        ("apps/data-pipeline/processing/analysis", "processing_analysis"),
        ("apps/data-pipeline/processing/features", "processing_features"),
        ("apps/data-pipeline/processing/extract", "processing_extract"),
        ("apps/data-pipeline/processing/tools/share", "processing_tools_share"),
        ("apps/data-pipeline/evaluation/feasibility", "evaluation_feasibility"),
        ("apps/data-pipeline/evaluation/viability_tests", "evaluation_viability_tests"),
        ("apps/data-pipeline/evaluation/tests", "evaluation_tests"),
        (
            "apps/data-pipeline/evaluation/personal/experiments/"
            "SANDBOX_20260716_preprocess_pipeline/src",
            "sandbox_d1_src",
        ),
        (
            "apps/data-pipeline/evaluation/personal/experiments/"
            "SANDBOX_20260717_status_periodic_collection/src",
            "sandbox_d2_status_src",
        ),
        ("scripts", "scripts"),
    ):
        copy_dir(rel, code, dest_name, use_ignore=True)

    for rel in (
        "apps/data-pipeline/processing/requirements-pg.txt",
        "apps/data-pipeline/evaluation/requirements.txt",
        "apps/data-pipeline/collection/requirements.txt",
        "apps/data-pipeline/AGENTS.md",
        "AGENTS.md",
        "docs/팀공유/최종패키지_명령_초안_20260806.md",
        "docs/팀공유/최종패키지_조장전달_목록_20260809.md",
    ):
        copy_file(rel, code / "00_가이드")

    (code / "README_코드.md").write_text(
        f"""# DA① 재현 코드 묶음

생성: {datetime.now(KST).isoformat(timespec="seconds")}

이 폴더는 **문서가 아니라 실행 코드**다. 조장/②가 같은 산출을 다시 만들 때 쓴다.

## 포함

| 폴더 | 내용 |
|---|---|
| processing_analysis | ETA·라벨·derived_v0·replay·품질 게이트 등 |
| processing_features | 피처 생성 |
| processing_extract | 일일 덤프·조인 |
| sandbox_d1_src / sandbox_d2_status_src | D1 스냅 · D2 패널 빌더 |
| evaluation_feasibility | tick 패널 복원 |
| evaluation_tests | pytest |
| scripts | pull / evening rebuild 등 |

## 금지

- `.env` / 키는 **절대 없음**. 각자 repo `.env` 사용.
- 점수·추천 서빙 코드는 ②/BE 영역 (여기 없음).

## 대표 재실행 (repo 루트 기준)

```powershell
# 라벨만 (ETA 테이블 있을 때)
python apps/data-pipeline/processing/analysis/build_station_eta_and_labels.py --labels-only
python apps/data-pipeline/processing/analysis/attach_derived_v0_features.py

# 8/9 전체 순서는 00_가이드/최종패키지_명령_초안_20260806.md
```

```
DA① code pack | {stamp}
```
""",
        encoding="utf-8",
    )

    readme = f"""# EV SafeCharge — DA① → 조장님 **풀팩** (데이터 + 코드)

- 생성: {datetime.now(KST).isoformat(timespec="seconds")}
- 포함: 핸드오프 + **가공/라벨 parquet** + **원천 CSV** + **재현 코드**
- 상세 목록: `00_먼저읽기/최종패키지_조장전달_목록_20260809.md`
- **`.env` / API 키는 포함하지 않음**

## 읽는 순서

1. `README_먼저읽기.md` (이 파일)
2. `00_먼저읽기/최종패키지_조장전달_목록_20260809.md`
3. `00_먼저읽기/팀공유_핸드오프_①to②_*.md`
4. **모델 타겟** → `02_모델테스트_가공본/arrival_labels_tmap_eta_v1_with_derived.parquet`
5. **규칙 입력** → `02_.../station_feature_snapshot_latest.*`
6. **재현/수정** → `06_재현코드_DA1/`
7. 원천 확인 → `04_원천수집_CSV/`

## 폴더

| 폴더 | 내용 |
|---|---|
| 00_먼저읽기 | 계약·핸드오프·핵심갭·파생 |
| 01_피처적합도_유의성 | 적합도·schema |
| 02_모델테스트_가공본 | D1·D2·ETA·도착라벨+derived·training·replay |
| 03_커버리지_주차 | 한계 문서 |
| 04_원천수집_CSV | status·UTIC·소통·usage·info·조인 |
| 05_품질리포트 | monitor·dedupe·추이 |
| **06_재현코드_DA1** | **파이썬/스크립트 재현 묶음** |

## 한 줄

- md만 보내지 않는다. **02 데이터 + 06 코드**가 본체다.
- 학습 주력 타겟: 도착 라벨 with_derived.
- usage/주차점수/`eta_is_proxy` 학습입력 금지.
- 서빙 ETA = BE TMAP.

```
DA① full pack data+code | {stamp}
```
"""
    (out_dir / "README_먼저읽기.md").write_text(readme, encoding="utf-8")

    print("zipping...", flush=True)
    zip_path = DESK / f"{folder_name}.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path in out_dir.rglob("*"):
            if path.is_file():
                zf.write(path, arcname=str(path.relative_to(out_dir.parent)))

    meta = {
        "folder": str(out_dir),
        "zip": str(zip_path),
        "zip_bytes": zip_path.stat().st_size,
        "copied_n": len(copied),
        "missing": missing,
        "includes_code": True,
        "includes_arrival_labels_derived": True,
        "excludes_secrets": True,
        "note": "full raw+processed+code pack",
    }
    (out_dir / "pack_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with zipfile.ZipFile(zip_path, "a", zipfile.ZIP_DEFLATED) as zf:
        zf.write(
            out_dir / "pack_meta.json",
            arcname=f"{folder_name}/pack_meta.json",
        )
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
