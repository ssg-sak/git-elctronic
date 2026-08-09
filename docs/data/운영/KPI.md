# DA➀ KPI — 수집·품질·핸드오프

| | |
|---|---|
| **담당** | AI·데이터 ① |
| **작성** | 2026-07-22 |
| **한 줄** | **매일 루프가 도는지 · D1이 쓸 만한지 · ②에게 넘길 숫자가 맞는지** |
| **관련** | [`가용률_수치기준.md`](./가용률_수치기준.md) · [`KPI_보고서.md`](./KPI_보고서.md) (**수치 보고서 · 자동 갱신**) · [`수집루프_쉬운설명.md`](./수집루프_쉬운설명.md) |

> 점수·추천 성공률 KPI는 **DA➁** 영역. 여기서는 **재료(데이터) KPI**만.

---

## 1. KPI 한눈에

| ID | KPI | 목표 (MVP) | 측정 | 빨간불 |
|---|---|---|---|---|
| **K1** | status 루프 연속성 | 가동 중 간격 **≈5분** · 당일 gap ≤2회 | `index.csv` · `status_daily/` | gap 다수 또는 간격 ≫10분 지속 |
| **K2** | EvCharger 일일 호출 | **≤ 800 / 1,000** (여유 20%) | `logs/daily_quota.json` | ≥900 |
| **K3** | UTIC 돌발 루프 | 가동 중 **≈15분** · extract OK | `loops/utic/*_meta_latest.json` | XML 파싱 실패·미갱신 >1h |
| **K4** | UTIC 조인 커버 | 1km 매칭 **>0** (돌발 있을 때) | `join_traffic_incident_utic_meta.json` | extract OK인데 join 0 지속 |
| **K5** | D1 관측 가용률 | 보고용으로만 · **절대값 단정 금지** | D1 `availability_ratio_observed` | — (추세·버킷으로) |
| **K6** | 확정 가용 충전소 비율 | **≥ 50%** | D1 `has_confirmed_available` | <40% 지속 |
| **K7** | 미관측률 | 평균 **≤ 0.5** | D1 `unobserved_rate` | >0.5 지속 |
| **K8** | D1 신선도 | 핸드오프 전 `as_of_ts` **당일·최근** | D1 메타 | as_of가 수 시간~일 전 |
| **K9** | mock 혼입 | D1 `traffic_is_mock=false` · `parking_is_mock=false` · `parking_source=team5_pis` | D1 플래그 | mock 거리 재투입 |
| **K10** | 일일 점검 health | `healthy` (또는 사유 기록) | `evaluation/results/status_daily/YYYY-MM-DD` | `unhealthy` 미기록 |
| **K11** | D1 미관측 충전소 비율 | 추세 모니터링 (절대 목표 고정 안 함) | D1 `observation_state=UNOBSERVED` 비율 | 급증·원인 미기록 |
| **K12** | info 일별 `statId` 증감 | 일일 덤프 diff 기록 | `daily/.../daegu_charger_info_*` | 덤프 공백 지속 |
| **K13** | 신축단지 시드 × info 이름 커버 | 샘플 대조 결과 보고 | `신축단지_인포대조_*` · `MISSING_IN_INFO` 수 | 시드 미갱신·미보고 |

> **범위:** MVP 재료는 **EvCharger에 등록·관측 가능한 충전소**. 신축 아파트 내부·미등록 충전기는 구조적 과소표집 가능 → “대구 완전 목록”을 KPI로 두지 않음.  
> 계획: [`커버리지갭_단계계획_20260731.md`](../../팀공유/커버리지갭_단계계획_20260731.md)

---

## 2. 운영 KPI (매일)

### K1 · status 루프
| 항목 | 값 |
|---|---|
| 주기 | 5분 호출 · API `period=10` |
| 저장 | SANDBOX `data/snapshots/` |
| 보는 법 | 당일 틱 수 · 간격 median · gap 목록 |

**7/21 기준 예시:** 72틱 · median 10분 · gap 1회(17:43~20:22) · health=healthy

### K2 · API 한도
| 항목 | 값 |
|---|---|
| 한도 | EvCharger **1,000콜/일** (다른 EvCharger와 공유) |
| 목표 | ≤800 · 여유 확보 |

**7/21 예시:** 372콜 (37%)

### K3–K4 · UTIC 돌발
| 항목 | 값 |
|---|---|
| 주기 | 15분 · extract → join |
| 저장 | `docs/data/loops/utic/` · 조인 `spatial_join/` |
| 키/IP | `UTIC_API_KEY` + 화이트리스트 (집/학원 분리) |

돌발 건수는 **날마다 변동** → KPI는 “루프·조인이 도는지”이지 건수 절대값이 아님.

---

## 3. 품질·가용 KPI (핸드오프·보고)

분모 규칙 정본: [`가용률_수치기준.md`](./가용률_수치기준.md)

| 쓸 말 | 지표 | 쓰지 말 것 |
|---|---|---|
| “관측된 충전기 중 대기 비율” | D1 `availability_ratio_observed` | 스냅샷 67% = 대구 전체 가용률 |
| “확정 가용 ≥1대 소 비율” | `has_confirmed_available` | |
| “미관측 비율” | `unobserved_rate` | 미관측 = 고장 |
| “전역 대수비” | `available/total` | 대표 지표로 단독 사용 |

신뢰도: **HIGH+NORMAL vs CHECK** 비중 (≤5분 / ≤15분 / >15분).

---

## 4. 산출물·위치

| 산출 | 경로 |
|---|---|
| status 스냅샷 | `docs/data/loops/loop1/snapshots/` |
| status 일일 | `apps/data-pipeline/evaluation/results/status_daily/` |
| UTIC CSV·meta | `docs/data/loops/utic/` |
| UTIC 조인 | `docs/data/spatial_join/join_traffic_incident_utic_*` |
| D1 | `evaluation/results/datasets/station_feature_snapshot_latest.*` |
| D2 | `evaluation/results/datasets/station_feature_panel_*` |

---

## 5. 점검 루틴 (짧게)

**아침 / 루프 켠 뒤**
1. status·UTIC 프로세스 살아 있는지  
2. 최신 스냅샷·`utic_*_latest` 시각이 최근인지  

**저녁 / 끄기 전**
1. 당일 틱 수 · 호출 수 (K1·K2)  
2. UTIC 마지막 성공 시각 (K3)  
3. (선택) D1 재빌드 후 K5–K8 한 줄 기록  

**② 핸드오프 전**
1. D1 `as_of_ts` 갱신 (K8)  
2. mock 플래그 확인 (K9)  
3. [`팀공유_핸드오프`](../../팀공유/팀공유_핸드오프_①to②_20260720.md) 수치 갱신  

---

## 6. 기준선 메모 (갱신란)

> **현재 수치 보고서:** [`KPI_보고서.md`](./KPI_보고서.md) — 매일/점검 시  
> `python apps/data-pipeline/processing/analysis/report_kpi.py`

| 날짜 | K1 틱 | K2 콜 | K3 UTIC | K6 확정가용 | 비고 |
|---|---:|---:|---|---:|---|
| 2026-07-21 | 72 | 372 | 낮 성공·저녁 IP이슈 | 64.5% (D1 10:01) | gap 1 · health OK |
| 2026-07-22 | (루프 가동 중) | (기입) | 학원키 재가동 | **69.6%** (D1 13:36) | D1 재빌드 · **linkspeed 1,960 추출** · 주차만 D1 공백 |
| 2026-07-23 | — | — | — | (D1 20:49 재빌드) | **주차 team5 조인·D1** · K9=`team5_pis`/mock=false · [기록](../주차/주차_조인_D1_기록_20260723.md) |
| 2026-07-31 | 49 (오전) | 223 | 대구 5 · 조인 287 | **79.7%** (D1 08:12) | OK 9/10 · D2 latest 동기화 · [팀 핸드오프](../../팀공유/D1_KPI_핸드오프_20260731.md) |

---

## 6b. 커버리지 갭 KPI (K11–K13)

| ID | 보는 법 | 비고 |
|---|---|---|
| K11 | D1 `UNOBSERVED` / 전체 | “미관측≠고장”. Type B 갭 |
| K12 | 어제·오늘 info `statId` set diff | 신규 노출 후보만 (신설 확정 아님) |
| K13 | 신축 입주 시드 단지명 ⊆ info `statNm` | Type A 샘플 모니터링 · [1차 결과](../../팀공유/신축단지_인포대조_20260731/README_쉬운설명.md) |

스크립트: `processing/tools/share/compare_new_apt_vs_info.py` · `probe_info_coverage_gaps.py`

---

## 7. 범위 밖 (②·백엔드)

| 항목 | 담당 |
|---|---|
| 추천 Top-N 적중·실패위험 등급 정확도 | DA➁ |
| ETA·TMAP 응답시간 | 백엔드 |
| 앱 전환·체류 | 프론트·기획 |

```
DA➀ | KPI | 2026-07-22
```
