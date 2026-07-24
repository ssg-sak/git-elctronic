# 공공 API 연동 현황 (현재)

| | |
|---|---|
| **담당** | AI·데이터 ① |
| **갱신** | 2026-07-22 |
| **정본** | 본 문서 · 과거 스냅샷은 [`../_archive/data/`](../_archive/data/) |

> 키 값은 적지 않는다. 로컬 `.env` + [`apps/data-pipeline/AGENTS.md`](../../../apps/data-pipeline/AGENTS.md) 표 참고.

---

## 1. 한 줄

`DATA_GO_KR_KEY` 하나로 EvCharger·Tour·**대구 교통(소통·돌발)** 등 호출.  
돌발은 **UTIC 병행 중** → 공공 `dgincident`로 전환 검토. 주차는 **KOTSA 대기(7/23+)**.  
**기상(S03~S05)은 2026-07-22 팀 합의로 수집·활용 중단.**

> **2026-07-22**: 대구 `linkspeed`/`dgincident` **404 복구 확인** · 소통 1,960링크 추출 → [`교통소통_데이터_보고.md`](../품질보고/교통소통_데이터_보고.md)

---

## 2. 키

| 변수 | 용도 | 상태 |
|---|---|---|
| `DATA_GO_KR_KEY` | 충전·Tour·대구 교통 등 | 사용 중 · **Decoding** 키로 Body 전달 |
| `UTIC_API_KEY` | 돌발 개방데이터 | 사용 중 · **지금=학원 등 기존 IP에서 루프** · 집 대역 `124.61.255.0/24`는 **집 수집용(예약)** |
| `TMAP_APP_KEY` | ETA·POI | 백엔드/시험 · MVP ETA는 백엔드 |
| `KAKAO_REST_KEY` | 로컬 카테고리 | 보류 · [`카카오_로컬_API.md`](../API/카카오_로컬_API.md) |
| `DAEGU_PARKING_*` | 대구 주차 PIS | AWS IP만 · **미사용** |

- 신규·재발급 후 ~1시간 `401`/`403` → 동기화 대기  
- **404 ≠ 미승인** (경로·원본 서버 문제)

---

## 3. 데이터별 현재

| 데이터 | 호출 | 저장 | 비고 |
|---|---|---|---|
| 충전기 info | ✅ | `extracted/daegu_charger_info_*` | 단발 재추출 |
| 충전기 status | ✅ 루프 | `loops/loop1/snapshots/` | 5분 · `period=10` · `extracted` 금지 |
| ~~기상~~ | **중단** | — | 2026-07-22 팀 합의 |
| Tour / 산책 / 시관광 | ✅/혼합 | `extracted/` | |
| 돌발 (UTIC) | ✅ 루프 | `loops/loop2/` | 대구 필터 · 공공 dgincident와 **병행 검증** |
| **교통 소통 (대구 ITS)** | ✅ 루프 | `loops/loop3/` | **15분** · 1,960 링크 · `run_daegu_traffic_loop.py` |
| **교통 돌발 (대구 ITS)** | ✅ **복구** | `loops/loop3/` | 진행 중 건만 · 좌표 있음 |
| 주차 KOTSA | ⏳ 502/대기 | — | [`주차교통_대체API_전략.md`](../API/주차교통_대체API_전략.md) |
| 주차 mock | 보관만 | `extracted/*_mock` | D1 거리 미투입 |

---

## 4. 관련 정본

| 문서 | 내용 |
|---|---|
| [`교통소통_데이터_보고.md`](../품질보고/교통소통_데이터_보고.md) | 소통·돌발 설명 · 7/22 복구 |
| [`UTIC_개방데이터_준수사항.md`](../API/UTIC_개방데이터_준수사항.md) | UTIC 출처·준수 |
| [`수집루프_쉬운설명.md`](./수집루프_쉬운설명.md) | status·UTIC 루프 |
| [`실데이터_목데이터_트랙.md`](./실데이터_목데이터_트랙.md) | 실 vs 목 · D1 플래그 |
| 과거 통합 스냅샷 (7/16) | [`../_archive/data/공공API_연동현황_통합_20260716.md`](../../_archive/data/공공API_연동현황_통합_20260716.md) |

```
DA➀ | API status current | 2026-07-22
```
