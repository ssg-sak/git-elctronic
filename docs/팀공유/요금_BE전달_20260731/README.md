# 충전 요금 — 백엔드 전달 패키지 (2026-07-31)

**수신:** 백엔드  
**제공:** AI·데이터 ①  

---

## 한 줄

**운영사 요금표(ev.or.kr)로 대구 충전소 약 97%에 단가 힌트를 붙일 수 있다.**  
다만 `statId` 고유 요금이 아니라 **운영사×용량구분(완속/급속)·회원/비회원** 단가다.

---

## 전달 파일 (우선 이것)

| 파일 | 용도 |
|---|---|
| [`fee_tariff_ref_operator_evorkr_20260731.csv`](./fee_tariff_ref_operator_evorkr_20260731.csv) | 운영사 단가 정본 (232행 · 103사) |
| [`daegu_station_operator_fee_hint.csv`](./daegu_station_operator_fee_hint.csv) | 대구 `statId` → 운영사 단가 힌트 (**4087/4210**) |
| [`fee_tariff_ref_kepco_latest.csv`](./fee_tariff_ref_kepco_latest.csv) | 한전 계시별 단가 (보조) |
| [`충전요금_매핑_담당정리_20260730.md`](./충전요금_매핑_담당정리_20260730.md) | 역할·금지 |
| [`README_operator_fee.md`](./README_operator_fee.md) | 운영사표 짧은 메모 |

---

## 매칭 결과

| 항목 | 값 |
|---|---:|
| 요금 행 / 운영사 | 232 / 103 |
| 대구 소 매칭 | **4,087 / 4,210 (97.1%)** |
| match_level | `OPERATOR_TYPE` |
| 미매칭 예 | 차지인, 씨어스, GS칼텍스 일부 등 (~123소) |

---

## BE 사용법

1. `daegu_station_operator_fee_hint.csv`로 `statId` → `fee_operator_nm`  
2. 충전기 용량(완속/급속)에 맞는 행을 운영사 표에서 고름  
3. 회원/비회원·요청 시각 정책에 따라 `member` / `nonmember` 원/kWh  
4. 매칭 실패 → null (`NONE`)

**금지:** 추천 점수 가중치 즉시 반영 · 미매칭을 평균으로 채우기 · ETA 대체

```
DA① → BE | operator fee OPERAT OR_TYPE 97% | 2026-07-31
```
