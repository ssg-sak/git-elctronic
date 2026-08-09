"""Refresh README/meta inside docs/팀공유/최종본_20260809 after D1 rebuild."""
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

REPO = Path(__file__).resolve().parents[5]
KST = ZoneInfo("Asia/Seoul")
OUT = REPO / "최종본_20260809"
DATASETS = REPO / "apps" / "data-pipeline" / "evaluation" / "results" / "datasets"
ARCH = REPO / "docs" / "data" / "loops" / "_archive"


def main() -> None:
    df = pd.read_csv(DATASETS / "station_feature_snapshot_latest.csv", usecols=["as_of_ts"], nrows=3)
    as_of = str(df["as_of_ts"].iloc[0])
    pull = (ARCH / "from_lightsail_latest.txt").read_text(encoding="utf-8-sig").strip()

    dest = OUT / "05_모델데이터"
    dest.mkdir(parents=True, exist_ok=True)
    for name in [
        "station_feature_snapshot_latest.csv",
        "station_feature_snapshot_latest.parquet",
        "station_feature_snapshot_with_eta_derived_latest.csv",
        "station_feature_snapshot_with_eta_derived_latest.parquet",
        "station_feature_panel_latest.parquet",
        "station_tmap_eta_latest.csv",
        "arrival_labels_tmap_eta_v1_with_derived.parquet",
        "station_horizon_training_v1.parquet",
    ]:
        src = DATASETS / name
        if src.is_file():
            shutil.copy2(src, dest / name)

    now = datetime.now(KST).isoformat(timespec="seconds")
    readme = f"""# 최종본_20260809 — DA① 로컬 정본

| | |
|---|---|
| **위치** | `docs/팀공유/최종본_20260809/` |
| **생성** | {now} |
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

## 참고

- 현재표는 **8/9 pull 반영 재생성분** (as_of 위).
- 시간표 풀 재생성은 메모리 부하로 중단됐을 수 있음 → `05` panel 파일 시각 확인.
- UTIC 신규 extract는 IP 거부로 기존 조인 유지.

```
DA① | FINAL 20260809 | local pack
```
"""
    (OUT / "README.md").write_text(readme, encoding="utf-8")
    (OUT / "00_먼저읽기" / "README.md").write_text(readme, encoding="utf-8")
    meta = {
        "stamp": "20260809",
        "generated_at": now,
        "out": "docs/팀공유/최종본_20260809",
        "as_of": as_of,
        "pull": pull,
    }
    (OUT / "pack_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "as_of": as_of, "pull": pull}, ensure_ascii=True))


if __name__ == "__main__":
    main()
