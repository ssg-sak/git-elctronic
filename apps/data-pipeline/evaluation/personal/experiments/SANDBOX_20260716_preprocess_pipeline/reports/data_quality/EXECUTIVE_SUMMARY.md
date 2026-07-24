# Executive Summary — 전처리 파이프라인 결과

```
SSG-SAK  |  SANDBOX_20260716_preprocess_pipeline  |  2026-07-16
```

격리 샌드박스에서 전 소스 CSV를 읽어 관계형 정제 테이블을 생성했다.  
원본 `docs/data/extracted/` 는 **수정하지 않았다**.

---

## 1. 어떤 결측치를 복원했는지

| 항목 | 방법 |
|---|---|
| status `statNm` (100% 결측) | `statId+chgerId` 로 info 조인 복원 |
| TourAPI 한글 깨짐 | 깨진 행만 `latin1→utf-8` 시도, `encoding_repaired` 기록 |
| 주차 전일운영 + 시간 공백 | `0000`/`2400` **파생 컬럼** (원본 결측 보존) |

## 2. 어떤 결측치를 유지했는지

| 항목 | 처리 |
|---|---|
| status 미수집 (~97.66%) | `status_missing` / `NO_STATUS_OBSERVED` — **사용 불가 아님** |
| `output` 결측 | `output_missing=True` (평균 대체 금지) |
| `useTime` 결측 | `operation_time_known=False` (24시간 가정 금지) |
| `parkingFree` 결측 | `UNKNOWN` |
| 주차 실시간 없는 2곳 | `realtime_status=UNKNOWN` (만차 아님) |
| 공원 `roadNmAddr` | 행 유지, `address_source=LOT` |
| city_tour 좌표/email | 좌표 미생성, email 원본 보존 |

## 3. 어떤 데이터를 분석에서 제외했는지

| 제외 | 이유 |
|---|---|
| `*_mock(1).csv` | 원본과 동일 복사본 |
| 좌표 이상 ~27건 **삭제** | 삭제 안 함 → `data/quarantine/` 격리 |
| 도착 시 예측 ML 학습 | 스냅샷만으로는 부족 (보류) |

## 4. 현재 데이터만으로 가능한 분석

- 충전기 master / status 커버리지·품질 플래그 기반 **규칙형** 추천 피처
- 주차·교통 **mock** 조인 실험 (EXP-002)
- 좌표 있는 POI (Tour 복구분 + 공원) 밀도
- city_tour 속성 long/wide (지오코딩 전)
- 기상 **단일 격자** hourly wide (전역 날씨 해석 금지)

## 5. 추가 수집이 필요한 데이터

- 충전기 status **전체 스냅샷·시계열**
- city_tour **지오코딩**
- 기상 **다중 격자**
- 교통 API 복구 후 실데이터
- 카카오·TMAP 실키

---

## 핵심 수치 (파이프라인 실행 결과)

| 지표 | 값 |
|---|---|
| status 충전기 커버리지 | **2.3406%** |
| 좌표 품질 격리 행 | **27** |
| 산출 테이블 수 | 17 |

상세: `reports/data_quality/data_quality_report.md`, `missing_value_policy.md`
