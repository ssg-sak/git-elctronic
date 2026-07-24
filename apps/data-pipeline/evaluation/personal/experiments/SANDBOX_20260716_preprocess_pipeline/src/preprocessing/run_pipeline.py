"""
End-to-end preprocessing pipeline for SANDBOX_20260716_preprocess_pipeline.
Does NOT modify docs/data/extracted originals.
"""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

import pandas as pd

# Allow `python .../run_pipeline.py` without installing package
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))  # src/
sys.path.insert(0, str(ROOT))  # preprocessing/

from preprocessing import paths  # noqa: E402
from preprocessing.load_data import load_all  # noqa: E402
from preprocessing.clean_charger import (  # noqa: E402
    build_charger_tables,
    clean_charger_info,
    clean_charger_status,
)
from preprocessing.clean_parking import clean_parking  # noqa: E402
from preprocessing.clean_poi import (  # noqa: E402
    clean_city_tour,
    clean_tour_attractions,
    clean_walk_parks,
    match_tour_candidates,
)
from preprocessing.build_integrated_tables import build_poi_master, persist_all  # noqa: E402
from preprocessing.utils import missing_report, save_table  # noqa: E402


def _df_profile(name: str, df: pd.DataFrame) -> dict:
    return {
        "name": name,
        "rows": len(df),
        "cols": len(df.columns),
        "missing": missing_report(df).to_dict(orient="records"),
    }


def write_reports(ctx: dict) -> None:
    paths.REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (paths.REPORT_DIR / "pipeline_meta.json").write_text(
        json.dumps(ctx["meta"], ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )

    # missing policy
    policy = """# Missing Value Policy

## 복원 (join / rule)

| 항목 | 방법 |
|---|---|
| status `statNm` | info `statId+chgerId` 조인 복원 |
| 주차 전일운영 + 시간 공백 | `00:00`/`24:00` **파생** (원본 결측 보존) |
| Tour 한글 깨짐 | 깨진 행만 latin1→utf-8 복구 시도, `encoding_repaired` 기록 |

## 유지 (추정 금지)

| 항목 | 처리 |
|---|---|
| status 미수집 | `status_missing=True` / `NO_STATUS_OBSERVED` — **사용불가 아님** |
| output 결측 | `output_missing=True` — 평균·유형 최빈값 대체 금지 |
| useTime 결측 | `operation_time_known=False` — 24시간 가정 금지 |
| parkingFree 결측 | `UNKNOWN` |
| 주차 실시간 없음 | `realtime_status=UNKNOWN` — 만차/혼잡 대체 금지 |
| 공원 roadNmAddr | 행 삭제 금지, `address_source=LOT` |
| city_tour email / Tour tel | 피처 제외 가능, 원본 보존 |
| 기상 코드형 SKY/PTY | 범주 유지 |

## 제외

| 항목 | 이유 |
|---|---|
| `*(1).csv` 교통 mock 복사본 | 내용 동일 중복 |
| city_tour 좌표 | 없음 → 임의 생성 금지, 지오코딩 대기 테이블 분리 |
| 도착시 예측 모델 학습 | 단일 스냅샷 — status 시계열 추가 수집 필요 |

## 격리

| 항목 | 위치 |
|---|---|
| 좌표 품질 이상 충전기 | `data/quarantine/charger_coordinate_suspects.*` (삭제 아님) |
"""
    (paths.REPORT_DIR / "missing_value_policy.md").write_text(policy, encoding="utf-8")

    m = ctx["meta"]
    ch = m.get("charger", {})
    lines = [
        "# Data Quality Report — SANDBOX_20260716_preprocess_pipeline",
        "",
        "## 범위",
        "- 원본: `docs/data/extracted/` (읽기 전용)",
        "- 산출: 본 샌드박스 `data/processed/`",
        "- 제외: `daegu_traffic_*_mock(1).csv`",
        "",
        "## 파일별 규모",
    ]
    for p in ctx.get("profiles_raw", []):
        lines.append(f"- **{p['name']}**: {p['rows']} rows × {p['cols']} cols")

    lines += [
        "",
        "## 상태정보 수집 커버리지",
        f"- 충전기 기준: **{ch.get('coverage_charger_pct')}%** (status rows={ch.get('status_rows')} / info={ch.get('info_rows')})",
        f"- 충전소 기준: **{ch.get('coverage_station_pct')}%**",
        "- 해석: 변경분(`period`) 수집 → **미관측 ≠ 사용 불가**",
        "",
        f"## 좌표 이상(격리) 건수: {ch.get('quarantine_rows')}",
        "- 파일: `data/quarantine/charger_coordinate_suspects.csv`",
        "",
        f"## Tour 인코딩 복구 행수: {m.get('tour', {}).get('encoding_repaired_rows')}",
        "",
        "## 주차",
        f"- 기본만 있고 실시간 없음: `{m.get('parking', {}).get('info_without_realtime')}` → UNKNOWN",
        "",
        "## 목데이터",
        "- parking_*, traffic_linkspeed_mock, traffic_incident_mock (`isMock=True` 유지)",
        "",
        "## 조인",
        f"- statNm join restored rows (info match): {ch.get('statNm_restored_via_join')}",
        f"- tour↔city match candidates: {m.get('poi', {}).get('match_candidates')}",
        "",
        "## 모델링에 바로 쓰기 어려운 것",
        "- status 미관측 다수 → 가용률 왜곡 위험",
        "- 단일 시점 스냅샷 → 도착시 예측 학습 부족",
        "- city_tour 무좌표",
        "- Tour 인코딩 이슈(복구 시도함)",
        "",
        "## 산출 테이블",
    ]
    for name in sorted(ctx.get("tables", {}).keys()):
        lines.append(f"- `{name}` → `data/processed/{name}.csv|.parquet`")

    (paths.REPORT_DIR / "data_quality_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # quarantine list excerpt
    qpath = paths.QUARANTINE_DIR / "charger_coordinate_suspects.csv"
    if qpath.exists():
        q = pd.read_csv(qpath, dtype="string")
        cols = [c for c in ["statId", "chgerId", "statNm", "addr", "lat", "lng", "coordinate_quality_flag"] if c in q.columns]
        excerpt = q[cols].head(50)
        save_table(excerpt, paths.REPORT_DIR / "coordinate_suspects_sample")


def run() -> dict:
    raw = load_all()
    meta: dict = {}
    profiles_raw = [_df_profile(k, v) for k, v in raw.items()]

    info_c, quarantine, meta_info = clean_charger_info(raw["charger_info"])
    # need pk on info before status
    status_c, meta_st = clean_charger_status(raw["charger_status"], info_c)
    meta["charger"] = {**meta_info, **meta_st}
    charger_tables = build_charger_tables(info_c, status_c)

    parking, meta_park = clean_parking(raw["parking_info"], raw["parking_realtime"])
    meta["parking"] = meta_park

    tour, meta_tour = clean_tour_attractions(raw["tour_attractions"])
    city, city_long, city_wide_attrs, meta_city = clean_city_tour(raw["city_tour"])
    parks, meta_park_walk = clean_walk_parks(raw["walk_parks"])
    matches = match_tour_candidates(tour, city)
    meta["tour"] = meta_tour
    meta["city_tour"] = meta_city
    meta["walk"] = meta_park_walk
    meta["poi"] = {"match_candidates": len(matches)}

    poi_master, city_nocoord = build_poi_master(tour, parks, city)

    tables = {
        **charger_tables,
        "parking_current": parking,
        "poi_master": poi_master,
        "poi_city_tour_no_coords": city_nocoord,
        "poi_city_tour_attrs_long": city_long,
        "poi_city_tour_attrs_wide": city_wide_attrs,
        "poi_tour_city_match_candidates": matches,
        "walk_parks_clean": parks,
        "tour_attractions_clean": tour,
    }
    persist_all(tables)
    # interim dumps
    save_table(info_c.head(1000), paths.INTERIM_DIR / "charger_info_sample")
    save_table(quarantine, paths.INTERIM_DIR / "quarantine_coords")

    ctx = {"meta": meta, "profiles_raw": profiles_raw, "tables": tables}
    write_reports(ctx)

    summary = {
        "restored": [
            "status.statNm via info join",
            "Tour mojibake (conditional latin1→utf-8)",
            "parking 전일운영 empty hours → derived 0000-2400 (raw kept)",
        ],
        "kept_as_missing": [
            "status_missing chargers (NOT unavailable)",
            "output_missing",
            "operation_time_known=False",
            "parkingFree UNKNOWN",
            "realtime_parking_missing → realtime_status=UNKNOWN",
            "park roadNmAddr empty rows kept",
            "city_tour email / no coords",
        ],
        "excluded": [
            "traffic mock *(1).csv duplicates",
            "auto-delete of coordinate suspects (quarantined instead)",
            "arrival-time ML training (snapshot-only)",
        ],
        "possible_now": [
            "charger master/status coverage analysis",
            "rule-based features with quality flags",
            "parking/traffic mock join experiments",
            "POI with coords (tour+parks); city tour attrs long/wide",
        ],
        "need_more_data": [
            "full charger status snapshots / time series",
            "city_tour geocoding",
            "live traffic APIs when 404 fixed",
            "Kakao/TMAP real keys",
        ],
    }
    (paths.REPORT_DIR / "executive_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {"meta": meta, "summary": summary, "n_tables": len(tables)}


if __name__ == "__main__":
    try:
        result = run()
        print("PIPELINE OK")
        print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
        print("tables:", result["n_tables"])
        print("coverage%:", result["meta"]["charger"].get("coverage_charger_pct"))
        print("quarantine:", result["meta"]["charger"].get("quarantine_rows"))
    except Exception:
        traceback.print_exc()
        sys.exit(1)
