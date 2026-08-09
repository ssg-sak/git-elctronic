"""Build a highly visible FINAL showcase folder (current artifacts, morning 8/9).

Desktop: 00_최종본_DA1_조장전달_지금기준_YYYYMMDD/
Repo:    docs/팀공유/최종본_조장전달_지금기준_YYYYMMDD/
Also writes Desktop zip.
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
SHARE = REPO / "docs" / "팀공유"
KST = ZoneInfo("Asia/Seoul")
DATASETS = REPO / "apps" / "data-pipeline" / "evaluation" / "results" / "datasets"
QUALITY = REPO / "docs" / "data" / "quality"
ANALYSIS = REPO / "docs" / "data" / "analysis"

STAMP = datetime.now(KST).strftime("%Y%m%d")
FOLDER = f"00_최종본_DA1_조장전달_지금기준_{STAMP}"


def _cp_file(src: Path, dest: Path, missing: list[str], copied: list[str]) -> None:
    if not src.is_file():
        missing.append(str(src.relative_to(REPO)).replace("\\", "/") if src.is_relative_to(REPO) else str(src))
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    copied.append(str(dest))


def _cp_tree(src: Path, dest: Path, missing: list[str], copied: list[str]) -> None:
    if not src.exists():
        missing.append(str(src.relative_to(REPO)).replace("\\", "/") if src.is_relative_to(REPO) else str(src))
        return
    if dest.exists():
        shutil.rmtree(dest)
    if src.is_file():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    else:
        shutil.copytree(src, dest)
    copied.append(str(src.relative_to(REPO)).replace("\\", "/") if src.is_relative_to(REPO) else str(src))


def main() -> None:
    out = DESK / FOLDER
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    copied: list[str] = []
    missing: list[str] = []

    # --- 00 먼저읽기 (this README written later) ---
    d00 = out / "00_★먼저여기부터"
    d00.mkdir()

    # --- 01 계약·한계 ---
    d01 = out / "01_계약_한계_필독"
    docs01 = [
        SHARE / "이름_쉬운말_안내_20260808.md",
        SHARE / "최종패키지_조장전달_목록_20260809.md",
        SHARE / "최종파일명_확정_20260808.md",
        SHARE / "ETA_동대구고정_한계_조장필독_20260808.md",
        SHARE / "주차_realtime_428_한계_20260803.md",
        SHARE / "충전이력_usage_희소성_과적합_20260804.md",
        SHARE / "핵심갭_개선계획_20260806.md",
        SHARE / "파생변수_검토_도착라벨_20260806.md",
        SHARE / "팀공유_핸드오프_①to②_20260804.md",
        SHARE / "모델적합도_과적합_완료패키지_20260808.md",
        REPO / "docs" / "데이터파트_①_8월9일까지_로드맵.md",
    ]
    for p in docs01:
        _cp_file(p, d01 / p.name, missing, copied)

    # --- 02 EDA·KPI ---
    d02 = out / "02_EDA_KPI_보고서"
    _cp_file(SHARE / "EDA_KPI_보고서_20260808.md", d02 / "EDA_KPI_보고서_20260808.md", missing, copied)
    _cp_file(SHARE / "D1_KPI_핸드오프_20260808.md", d02 / "D1_KPI_핸드오프_20260808.md", missing, copied)
    _cp_file(REPO / "docs" / "data" / "운영" / "KPI_보고서.md", d02 / "KPI_보고서.md", missing, copied)
    _cp_tree(SHARE / "EDA_최종_20260808", d02 / "EDA_최종_20260808", missing, copied)
    for name in ("kpi_report_latest.json", "recommendation_input_monitor_latest.json"):
        _cp_file(QUALITY / name, d02 / name, missing, copied)

    # --- 03 시각자료 ---
    d03 = out / "03_시각자료_전체_AI해설팩"
    _cp_tree(SHARE / "시각자료_AI해설팩_20260808", d03 / "시각자료_AI해설팩_20260808", missing, copied)
    _cp_tree(SHARE / "최종본_통합_20260808", d03 / "최종본_통합_20260808", missing, copied)

    # --- 04 HGB 피처 ---
    d04 = out / "04_HGB_피처_적합_과적합"
    for name in (
        "피처선정_최종_HGB_도착ETA_20260808",
        "피처적합도_HGB_도착ETA_20260808",
        "과적합위험_HGB_도착ETA_20260808",
    ):
        _cp_tree(SHARE / name, d04 / name, missing, copied)
    for name in ("hgb_arrival_eta_fitness_20260808", "hgb_overfit_risk_20260808"):
        _cp_tree(ANALYSIS / name, d04 / name, missing, copied)

    # --- 05 모델 데이터 (지금 latest) ---
    d05 = out / "05_모델데이터_현재표_시간표_라벨"
    files05 = [
        "station_feature_snapshot_latest.csv",
        "station_feature_snapshot_latest.parquet",
        "station_feature_snapshot_latest_meta.json",
        "station_feature_snapshot_with_eta_derived_latest.csv",
        "station_feature_snapshot_with_eta_derived_latest.parquet",
        "station_tmap_eta_latest.csv",
        "station_tmap_eta_latest.parquet",
        "station_feature_panel_latest.parquet",
        "arrival_labels_tmap_eta_v1_with_derived.parquet",
        "station_horizon_training_v1.parquet",
        "derived_v0_schema.json",
        "feature_schema_v1.json",
    ]
    for name in files05:
        _cp_file(DATASETS / name, d05 / name, missing, copied)
    # handoff samples if any
    handoff = DATASETS / "handoff_to_model"
    if handoff.is_dir():
        _cp_tree(handoff, d05 / "handoff_to_model", missing, copied)
    # ETA team share sample
    _cp_tree(SHARE / "ETA_실제_라벨_20260808", d05 / "ETA_실제_라벨_팀공유_20260808", missing, copied)

    # --- 06 오늘 pull ---
    d06 = out / "06_오늘_Lightsail_pull"
    arch = REPO / "docs" / "data" / "loops" / "_archive"
    for name in (
        "from_lightsail_latest.txt",
        "from_lightsail_latest_PULL_META.json",
        "PULL_LOG.md",
    ):
        _cp_file(arch / name, d06 / name, missing, copied)
    # note: not full archive (too big)

    # --- 07 이름·파일명 ---
    d07 = out / "07_쉬운말_파일명"
    for name in ("이름_쉬운말_안내_20260808.md", "최종파일명_확정_20260808.md"):
        _cp_file(SHARE / name, d07 / name, missing, copied)

    # PATHS pointer for huge originals
    (d05 / "원본경로_안내.txt").write_text(
        "\n".join(
            [
                "이 폴더의 표는 repo datasets/ 최신본을 복사한 것.",
                f"원본: {DATASETS}",
                "시간표 parquet ≈ 37MB · 라벨 ≈ 10MB 포함됨.",
                "tick 패널이 datasets에 없으면 누락(missing)으로 pack_meta에 기록.",
                "재빌드 전 컷오프: 현재표/시간표는 아직 2026-08-08 오전분일 수 있음.",
                "오늘(8/9) pull은 06_오늘_Lightsail_pull 참고 · 표 재생성은 별도.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    readme = f"""# ★ 최종본 — DA① → 조장 (지금 기준)

| | |
|---|---|
| **폴더** | `{FOLDER}` |
| **만든 시각** | {datetime.now(KST).isoformat(timespec="seconds")} |
| **오늘 pull** | `from_lightsail_20260809_072742` (+120 status / +160 traffic) |
| **표 컷오프** | 재빌드 전이면 **2026-08-08 11:17** 현재표·시간표일 수 있음 |
| **점수** | **없음** → ② |
| **상태** | 포장용 쇼케이스 (풀원천·재현코드 풀팩은 `pack_da1_lead_handoff` 별도) |

---

## 읽는 순서 (이 순서만)

1. **`00_★먼저여기부터/`** ← 이 파일
2. **`01_계약_한계_필독/`** — 동대구 ETA · 주차 금지 · usage HOLD · 조장 전달 목록
3. **`02_EDA_KPI_보고서/`** — EDA+KPI 한 장 · EDA 최종
4. **`05_모델데이터_현재표_시간표_라벨/`** — 학습·규칙 MVP 입력 표
5. **`04_HGB_피처_적합_과적합/`** — 최종 피처 9개 · 과적합 PASS
6. **`03_시각자료_전체_AI해설팩/`** — 그림 + AI 해설 브리핑
7. **`06_오늘_Lightsail_pull/`** — 8/9 아침 pull 메타

---

## 폴더 한눈에

| 폴더 | 뭐가 있나 |
|---|---|
| `00_★먼저여기부터` | 본 README |
| `01_계약_한계_필독` | 조장 필독 md |
| `02_EDA_KPI_보고서` | EDA·KPI·모니터 JSON |
| `03_시각자료_전체_AI해설팩` | 그림 112장+ · 통합본 |
| `04_HGB_피처_적합_과적합` | BI·적합도·과적합 |
| `05_모델데이터_현재표_시간표_라벨` | **표 정본 복사** |
| `06_오늘_Lightsail_pull` | pull 메타 (원천 전체 아님) |
| `07_쉬운말_파일명` | 현재표/시간표 말 · 파일명 |

---

## 말하는 이름

- **현재표** = 예전 D1 · `station_feature_snapshot_latest.*`
- **시간표** = 예전 D2 · `station_feature_panel_latest.parquet`

---

## 주의 (지금 기준)

- 8/9 **pull은 끝났고**, 현재표·시간표·라벨 **재생성 전이면** 표는 여전히 0808.
- UTIC은 Lightsail에 없음 · K3는 FAIL일 수 있음.
- 주차 점수 금지 · 동대구 ETA는 학습용 고정 origin.
- 이 폴더는 **잘 보이게 모은 쇼케이스**. 원천 CSV 전부+재현코드 풀팩은 나중에 `pack_da1_lead_handoff.py`.

```
DA① | final showcase now | {STAMP}
```
"""
    (d00 / "README_먼저읽기.md").write_text(readme, encoding="utf-8")
    (out / "README_먼저읽기.md").write_text(readme, encoding="utf-8")

    meta = {
        "folder": FOLDER,
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "copied_n": len(copied),
        "missing": missing,
        "note": "showcase of current finals; full raw+code via pack_da1_lead_handoff",
    }
    (out / "pack_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    # repo mirror
    repo_out = SHARE / f"최종본_조장전달_지금기준_{STAMP}"
    if repo_out.exists():
        shutil.rmtree(repo_out)
    shutil.copytree(out, repo_out)

    # zip on desktop
    zip_path = DESK / f"{FOLDER}.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in out.rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(out.parent))

    print(
        json.dumps(
            {
                "ok": True,
                "desktop_folder": str(out),
                "desktop_zip": str(zip_path),
                "repo_folder": str(repo_out),
                "zip_mb": round(zip_path.stat().st_size / (1024 * 1024), 2),
                "missing": missing,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
