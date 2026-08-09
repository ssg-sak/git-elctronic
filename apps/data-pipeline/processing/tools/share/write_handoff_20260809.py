"""Write ①→② handoff + KPI handoff stamped 20260809 from latest artifacts."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

REPO = Path(__file__).resolve().parents[5]
KST = ZoneInfo("Asia/Seoul")
SHARE = REPO / "docs" / "팀공유"
DS = REPO / "apps/data-pipeline/evaluation/results/datasets"
KPI = REPO / "apps/data-pipeline/evaluation/results/kpi_report_latest.json"
D2_META = DS / "handoff_to_model" / "HANDOFF_META_D2.json"
STATUS = "DA1_READY_FOR_DA2_MODEL_EVALUATION"


def main() -> None:
    snap = pd.read_parquet(DS / "station_feature_snapshot_latest.parquet")
    as_of = str(snap["as_of_ts"].iloc[0]) if "as_of_ts" in snap.columns else "?"
    n = len(snap)
    public = int(snap["recommend_public_default"].sum()) if "recommend_public_default" in snap.columns else None
    confirmed = (
        float(snap["has_confirmed_available"].mean())
        if "has_confirmed_available" in snap.columns
        else None
    )
    d2 = json.loads(D2_META.read_text(encoding="utf-8")) if D2_META.is_file() else {}
    kpi = json.loads(KPI.read_text(encoding="utf-8")) if KPI.is_file() else {}
    panel_max = "?"
    try:
        import pyarrow.parquet as pq

        t = pq.read_table(DS / "station_feature_panel_latest.parquet", columns=["panel_ts"])
        panel_max = str(pd.to_datetime(t.to_pandas()["panel_ts"]).max())
    except Exception as e:  # noqa: BLE001
        panel_max = f"(read_fail: {e})"

    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")
    handoff = f"""# ①→② 핸드오프 — 2026-08-09 (일 · 최종)

**수신:** AI·데이터 ② (모델·평가·서빙)  
**제공:** AI·데이터 ①  
**기준시각 (현재표 as_of):** `{as_of}`  
**상태:** **`{STATUS}`**  
**작성:** {now}

> 학습 ETA는 **동대구역 고정 origin**. 서빙 최종 3~5는 **BE 사용자 위치 TMAP**.  
> 점수·랭킹·추천 이유는 ② 영역 — ① 팩에 포함하지 않음.

---

## 전달 결론

| 항목 | 상태 | ②가 할 일 |
|---|---|---|
| 현재표(D1) | **사용 가능** | 후보 필터 + 규칙 점수 |
| 시간표(D2) | **사용 가능** · 끝시각 ≈ `{panel_max}` | 학습·replay 입력 |
| ETA | 동대구 고정 실측 (학습용) | 서빙은 BE TMAP |
| 주차 점수 | **넣지 말 것** | UX 보조만 |
| usage | HOLD_SPARSE · MVP 제외 | 보조 prior만 |
| 신선도 | observation_* + grade | UI 경고 (등급 완화 금지) |

---

## 핵심 경로

```text
apps/data-pipeline/evaluation/results/datasets/station_feature_snapshot_latest.parquet
apps/data-pipeline/evaluation/results/datasets/station_feature_panel_latest.parquet
apps/data-pipeline/evaluation/results/datasets/station_tmap_eta_latest.parquet
apps/data-pipeline/evaluation/results/datasets/arrival_labels_tmap_eta_v1_with_derived.parquet
apps/data-pipeline/evaluation/results/datasets/station_horizon_training_v1.parquet
apps/data-pipeline/evaluation/results/datasets/handoff_to_model/
docs/팀공유/최종패키지_조장전달_목록_20260809.md
```

---

## 당일 수치

| 지표 | 값 |
|---|---:|
| 현재표 행 | **{n}** |
| 공용 기본 후보 | {public if public is not None else "—"} |
| 확정 가용 비율 | {f"{confirmed:.1%}" if confirmed is not None else "—"} |
| 시간표 행 | **{d2.get("rows", "—")}** |
| 시간표 스냅 | **{d2.get("panel_timestamps", "—")}** |
| 시간표 충전소 | **{d2.get("stations", "—")}** |
| 오늘 pull | `from_lightsail_20260809_072742` |
| KPI JSON | `apps/.../kpi_report_latest.json` |

숫자 요약: [`D1_KPI_핸드오프_20260809.md`](./D1_KPI_핸드오프_20260809.md)

---

## 최종 9피처 (학습 계약)

`available_count`, `total_chargers`, `known_charger_count`, `observation_coverage`,  
`hour`, `weekday`, `avail_rate_lag_15m`, `avail_rate_lag_60m`, `tmap_eta_min`

타겟: `target_available_at_arrival`

---

## 금지

- usage / 주차점수 / `eta_is_proxy` 학습 입력
- ① 동대구 ETA를 런타임 사용자 ETA로 사용
- ①가 추천 점수·Top-N·추천 이유 산출

---

## 상태 문구

```
{STATUS}
```

이 상태는 **데이터셋 전달 가능**이지, 모델 성능·운영 채택 보장이 아니다.

```
DA① | handoff ①→② | 20260809 | {STATUS}
```
"""
    (SHARE / "팀공유_핸드오프_①to②_20260809.md").write_text(handoff, encoding="utf-8")

    kpi_md = f"""# 충전소 숫자·운영 KPI 핸드오프 (2026-08-09 · 최종)

| | |
|---|---|
| **현재표 as_of** | `{as_of}` |
| **상태** | `{STATUS}` |
| **시간표 끝** | `{panel_max}` |
| **시간표** | rows={d2.get("rows")} · snaps={d2.get("panel_timestamps")} · stations={d2.get("stations")} |
| **현재표 행** | {n} |
| **상세 JSON** | `apps/data-pipeline/evaluation/results/kpi_report_latest.json` |

조장 풀팩: `pack_da1_lead_handoff.py` → Desktop zip.

```
DA① | KPI handoff | 20260809
```
"""
    (SHARE / "D1_KPI_핸드오프_20260809.md").write_text(kpi_md, encoding="utf-8")

    # mirror into final pack first-read if present
    final = REPO / "최종본_20260809" / "00_먼저읽기"
    if final.is_dir():
        (final / "팀공유_핸드오프_①to②_20260809.md").write_text(handoff, encoding="utf-8")
        (final / "D1_KPI_핸드오프_20260809.md").write_text(kpi_md, encoding="utf-8")

    print(
        json.dumps(
            {
                "ok": True,
                "as_of": as_of,
                "status": STATUS,
                "d2_rows": d2.get("rows"),
                "panel_max": panel_max,
                "kpi_keys": list(kpi.keys())[:8],
            },
            ensure_ascii=True,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
