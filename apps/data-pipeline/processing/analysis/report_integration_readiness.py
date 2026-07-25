"""Report whether the current D1 integration can support the MVP.

This reports data coverage and constraints. It never calculates a recommendation
score or trains a model.

Usage (repo root):
  python apps/data-pipeline/processing/analysis/report_integration_readiness.py
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

import sys

_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))
from _bootstrap import ensure_paths

REPO = ensure_paths()
KST = ZoneInfo("Asia/Seoul")
D1 = REPO / "apps/data-pipeline/evaluation/results/datasets/station_feature_snapshot_latest.csv"
UTIC = REPO / "docs/data/spatial_join/join_traffic_incident_utic_1000m.csv"


def truth(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df:
        return pd.Series(False, index=df.index)
    return df[column].astype(str).str.lower().isin(("true", "1", "yes"))


def count_current_utic_matches() -> int | None:
    if not UTIC.is_file():
        return None
    join = pd.read_csv(UTIC, dtype=str)
    return int(join.get("matched", pd.Series(dtype=str)).str.lower().eq("true").sum())


def main() -> int:
    d1 = pd.read_csv(D1, low_memory=False)
    public = truth(d1, "recommend_public_default")
    coords = truth(d1, "coord_ok")
    available = truth(d1, "has_confirmed_available")
    parking = pd.to_numeric(d1.get("nearest_parking_m"), errors="coerce").notna()
    incident = pd.to_numeric(d1.get("nearest_incident_m"), errors="coerce").notna()
    parking_realtime = truth(d1, "parking_has_realtime")
    history = truth(d1, "history_observed")
    effective = d1.get(
        "reliability_grade_effective", pd.Series("UNKNOWN", index=d1.index)
    ).astype(str)

    stamp = datetime.now(KST).strftime("%Y%m%d")
    out = REPO / "docs/data/analysis" / f"integration_readiness_{stamp}"
    out.mkdir(parents=True, exist_ok=True)
    data = {
        "generated_at_kst": datetime.now(KST).isoformat(timespec="seconds"),
        "d1_as_of_ts": str(d1["as_of_ts"].iloc[0]),
        "d1_rows": int(len(d1)),
        "public_candidates": int(public.sum()),
        "public_candidates_coord_ok": int((public & coords).sum()),
        "public_confirmed_available": int((public & available).sum()),
        "public_available_coord_ok": int((public & available & coords).sum()),
        "parking_1km_static_matches": int(parking.sum()),
        "parking_realtime_matches": int(parking_realtime.sum()),
        "utic_matches_in_d1_snapshot": int(incident.sum()),
        "utic_matches_current_join": count_current_utic_matches(),
        "usage_history_matches": int(history.sum()),
        "reliability_effective_counts": {
            str(key): int(value) for key, value in effective.value_counts().items()
        },
        "mvp_verdict": "INPUT_READY_WITH_FRESHNESS_GUARD",
        "not_ready_for": [
            "arrival-success probability model",
            "parking congestion time profile",
            "route-specific ETA or traffic score",
        ],
    }
    (out / "summary.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    text = f"""# 데이터 통합 준비도 — MVP 입력 관점

| 항목 | 값 |
|---|---:|
| D1 기준시각 | {data["d1_as_of_ts"]} |
| 충전소 D1 행 | {data["d1_rows"]:,} |
| 공용 기본 후보 | {data["public_candidates"]:,} |
| 공용·좌표 정상 | {data["public_candidates_coord_ok"]:,} |
| 공용·확정 가용·좌표 정상 | {data["public_available_coord_ok"]:,} |
| Team5 주차 1km 정적 매칭 | {data["parking_1km_static_matches"]:,} |
| Team5 realtime 주차 연결 | {data["parking_realtime_matches"]:,} |
| UTIC 거리 피처 (D1 기준) | {data["utic_matches_in_d1_snapshot"]:,} |
| 이용이력 연결 | {data["usage_history_matches"]:,} |

## 결론

**MVP 규칙 추천의 입력 데이터는 결합되어 있다.** D1은 `statId` 한 행에 충전기 마스터·접근 제한·
상태 가용성·상태 신선도·운영시간·Team5 주차 거리/최신값·UTIC 돌발 거리·POI·과거 이용강도를
함께 보관한다. 따라서 API/모델 담당자는 공용·좌표 정상 후보에서 최신 상태와 신선도 경고를
반영하는 규칙 기반 추천을 구성할 수 있다.

다만 이 보고서는 **추천 성공 확률이 검증되었다는 뜻이 아니다.** 추천 순위 가중치와 ETA는
②/백엔드 영역이며, 현재 `eta_minutes`는 런타임 경로 API가 필요하다.

## 즉시 가능한 결과

- 공용 후보를 제한 충전소와 분리하고, 그중 확정 가용 충전소를 지도·목록 후보로 제시
- 상태 `reliability_grade_effective`와 `observation_age_minutes`를 경고로 표시
- 가까운 Team5 주차장 거리와, 값이 존재할 때만 최신 잔여면·점유율을 보조 정보로 표시
- UTIC 돌발 1km 거리와 과거 이용강도는 **보조 신호**로만 노출

## 아직 결론 내리면 안 되는 것

- 2주 누적 전 시간대별 충전 성공확률·장기 가용 패턴
- 주차 혼잡의 평소 패턴 (realtime 연결 범위와 이력이 아직 제한적)
- 링크속도만으로 만든 충전소별 이동시간/ETA

## 신선도 규칙

- 이 D1은 고정 스냅샷이다. Lightsail pull 또는 UTIC/주차 최신화 뒤에는 **D1 재빌드 전**
  현재 추천값으로 표현하지 않는다.
- D1 UTIC 조인 {data["utic_matches_in_d1_snapshot"]:,}개와 현재 조인
  {data["utic_matches_current_join"] or 0:,}개가 다를 수 있다. 이는 돌발 자체가 시시각각
  바뀌기 때문이며, 최종 전달 직전 재빌드로 일치시킨다.

```
DA① | integration readiness | {stamp}
```
"""
    (out / "README.md").write_text(text, encoding="utf-8")
    print(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"OUT {out.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
