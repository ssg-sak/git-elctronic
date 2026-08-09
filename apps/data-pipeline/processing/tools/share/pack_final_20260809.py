"""Create official local final pack at REPO ROOT: 최종본_20260809/

Full classified tree of current finals (docs + model tables + viz + HGB + pull meta).
Does not delete sources. Overwrites 최종본_20260809 if present.
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[5]
SHARE = REPO / "docs" / "팀공유"
OUT = REPO / "최종본_20260809"  # repo 최상위 (잘 보이게)
KST = ZoneInfo("Asia/Seoul")
DATASETS = REPO / "apps" / "data-pipeline" / "evaluation" / "results" / "datasets"
QUALITY = REPO / "docs" / "data" / "quality"
ANALYSIS = REPO / "docs" / "data" / "analysis"
OPS = REPO / "docs" / "data" / "운영"
ARCH = REPO / "docs" / "data" / "loops" / "_archive"


def _cp_file(src: Path, dest: Path, missing: list[str]) -> None:
    if not src.is_file():
        try:
            missing.append(str(src.relative_to(REPO)).replace("\\", "/"))
        except ValueError:
            missing.append(str(src))
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)


def _cp_tree(src: Path, dest: Path, missing: list[str]) -> None:
    if not src.exists():
        try:
            missing.append(str(src.relative_to(REPO)).replace("\\", "/"))
        except ValueError:
            missing.append(str(src))
        return
    if dest.exists():
        shutil.rmtree(dest)
    if src.is_file():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    else:
        shutil.copytree(src, dest)


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    missing: list[str] = []

    # 00
    d00 = OUT / "00_먼저읽기"
    d00.mkdir()
    for p in [
        SHARE / "이름_쉬운말_안내_20260808.md",
        SHARE / "최종패키지_조장전달_목록_20260809.md",
        SHARE / "최종패키지_명령_초안_20260806.md",
        SHARE / "최종파일명_확정_20260808.md",
        SHARE / "EDA_KPI_보고서_20260808.md",
        SHARE / "D1_KPI_핸드오프_20260808.md",
        SHARE / "모델적합도_과적합_완료패키지_20260808.md",
        SHARE / "ETA_동대구고정_한계_조장필독_20260808.md",
        SHARE / "팀공유_핸드오프_①to②_20260804.md",
        REPO / "docs" / "데이터파트_①_8월9일까지_로드맵.md",
    ]:
        _cp_file(p, d00 / p.name, missing)

    # 01 contracts
    d01 = OUT / "01_계약_한계"
    for p in [
        SHARE / "주차_realtime_428_한계_20260803.md",
        SHARE / "충전이력_usage_희소성_과적합_20260804.md",
        SHARE / "핵심갭_개선계획_20260806.md",
        SHARE / "파생변수_검토_도착라벨_20260806.md",
        SHARE / "커버리지갭_단계계획_20260731.md",
    ]:
        _cp_file(p, d01 / p.name, missing)
    _cp_tree(SHARE / "파생변수_derived_v0_20260806", d01 / "파생변수_derived_v0_20260806", missing)

    # 02 EDA KPI
    d02 = OUT / "02_EDA_KPI"
    _cp_file(SHARE / "EDA_KPI_보고서_20260808.md", d02 / "EDA_KPI_보고서_20260808.md", missing)
    _cp_file(OPS / "KPI_보고서.md", d02 / "KPI_보고서.md", missing)
    _cp_tree(SHARE / "EDA_최종_20260808", d02 / "EDA_최종_20260808", missing)
    for name in (
        "kpi_report_latest.json",
        "recommendation_input_monitor_latest.json",
        "recommendation_input_validate_latest.json",
    ):
        _cp_file(QUALITY / name, d02 / name, missing)

    # 03 viz
    d03 = OUT / "03_시각자료"
    _cp_tree(SHARE / "시각자료_AI해설팩_20260808", d03 / "시각자료_AI해설팩", missing)
    _cp_tree(SHARE / "최종본_통합_20260808", d03 / "최종본_통합_0808분류", missing)
    for name in (
        "시각화팩_통합_20260808",
        "상태수집_패널차트_20260808",
        "시간대_가용률_20260808",
        "도시혼잡_시계열_20260808",
        "돌발_UTIC_분석_20260808",
        "D1_최신화의미_20260808",
    ):
        # prefer 20260809 stamp if evening rebuild created it
        src09 = SHARE / name.replace("20260808", "20260809")
        src = src09 if src09.exists() else SHARE / name
        _cp_tree(src, d03 / src.name, missing)

    # 04 HGB
    d04 = OUT / "04_HGB_피처_과적합"
    for name in (
        "피처선정_최종_HGB_도착ETA_20260808",
        "피처적합도_HGB_도착ETA_20260808",
        "과적합위험_HGB_도착ETA_20260808",
    ):
        _cp_tree(SHARE / name, d04 / name, missing)
    for name in ("hgb_arrival_eta_fitness_20260808", "hgb_overfit_risk_20260808"):
        _cp_tree(ANALYSIS / name, d04 / name, missing)

    # 05 model data
    d05 = OUT / "05_모델데이터"
    for name in [
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
        "station_tick_panel.parquet",
        "derived_v0_schema.json",
        "feature_schema_v1.json",
    ]:
        _cp_file(DATASETS / name, d05 / name, missing)
    if (DATASETS / "handoff_to_model").is_dir():
        _cp_tree(DATASETS / "handoff_to_model", d05 / "handoff_to_model", missing)
    _cp_tree(SHARE / "ETA_실제_라벨_20260808", d05 / "ETA_실제_라벨_20260808", missing)
    replay = _latest(ANALYSIS, "arrival_availability_replay_")
    if replay:
        # lite: summaries only if huge
        size = sum(f.stat().st_size for f in replay.rglob("*") if f.is_file())
        if size > 80 * 1024 * 1024:
            dest = d05 / replay.name
            dest.mkdir(parents=True, exist_ok=True)
            for f in replay.rglob("*"):
                if not f.is_file():
                    continue
                if f.suffix.lower() in {".md", ".json", ".png", ".txt"} or f.stat().st_size < 2_000_000:
                    t = dest / f.relative_to(replay)
                    t.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, t)
            (dest / "FULL_PATH.txt").write_text(f"원본: {replay.resolve()}\n", encoding="utf-8")
        else:
            _cp_tree(replay, d05 / replay.name, missing)

    # 06 pull
    d06 = OUT / "06_수집_pull"
    for name in ("from_lightsail_latest.txt", "from_lightsail_latest_PULL_META.json", "PULL_LOG.md"):
        _cp_file(ARCH / name, d06 / name, missing)

    # readme
    as_of = "?"
    meta_snap = DATASETS / "station_feature_snapshot_latest_meta.json"
    if meta_snap.is_file():
        try:
            as_of = json.loads(meta_snap.read_text(encoding="utf-8")).get("as_of") or as_of
        except Exception:
            pass
    pull = ""
    latest_txt = ARCH / "from_lightsail_latest.txt"
    if latest_txt.is_file():
        pull = latest_txt.read_text(encoding="utf-8").strip()

    readme = f"""# 최종본_20260809 — DA① 로컬 정본

| | |
|---|---|
| **위치** | repo 최상위 `최종본_20260809/` |
| **생성** | {datetime.now(KST).isoformat(timespec="seconds")} |
| **현재표 as_of** | {as_of} |
| **오늘 pull** | `{pull}` |
| **점수** | 없음 → ② |
| **상태 목표** | `DA1_READY_FOR_DA2_MODEL_EVALUATION` |

이 폴더가 **8월 9일 최종본**이다. 팀/조장에게 넘길 때 **여기부터** 보면 된다.

---

## 폴더

| 폴더 | 내용 |
|---|---|
| `00_먼저읽기/` | 쉬운말·전달목록·EDA_KPI·동대구 ETA·로드맵 |
| `01_계약_한계/` | 주차 금지·usage HOLD·갭·파생 |
| `02_EDA_KPI/` | EDA 최종·KPI·모니터 |
| `03_시각자료/` | AI해설팩·가용률·패널·혼잡·UTIC |
| `04_HGB_피처_과적합/` | 최종 피처 9·적합·과적합 |
| `05_모델데이터/` | **현재표·시간표·ETA·라벨** |
| `06_수집_pull/` | Lightsail pull 메타 |

---

## 이름

- **현재표** = `station_feature_snapshot_latest.*`
- **시간표** = `station_feature_panel_latest.parquet`

```
DA① | FINAL 20260809 | local pack
```
"""
    (OUT / "README.md").write_text(readme, encoding="utf-8")
    (d00 / "README.md").write_text(readme, encoding="utf-8")

    meta = {
        "stamp": "20260809",
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "out": "최종본_20260809",
        "as_of": as_of,
        "pull": pull,
        "missing": missing,
    }
    meta["bytes"] = _dir_size(OUT)
    (OUT / "pack_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    # Windows console may be cp949 — avoid print crash on BOM paths
    summary = {
        "ok": True,
        "out": meta["out"],
        "as_of": meta.get("as_of"),
        "pull": meta.get("pull"),
        "bytes": meta["bytes"],
        "missing_n": len(missing),
        "missing": [m.replace("\ufeff", "") for m in missing],
    }
    print(json.dumps(summary, ensure_ascii=True, indent=2))


def _latest(parent: Path, prefix: str) -> Path | None:
    if not parent.is_dir():
        return None
    cands = sorted([p for p in parent.iterdir() if p.is_dir() and p.name.startswith(prefix)], key=lambda p: p.name)
    return cands[-1] if cands else None


def _dir_size(p: Path) -> int:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


if __name__ == "__main__":
    main()
