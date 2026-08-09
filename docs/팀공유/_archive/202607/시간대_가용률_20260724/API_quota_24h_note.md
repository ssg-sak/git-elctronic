# 전 시간대 status 수집 — EvCharger API 한도 대응 (DA①)

| | |
|---|---|
| **작성** | 2026-07-24 |
| **배경** | 히트맵 빈칸 = 그 시각 스냅 없음. 7/23 17~23시는 **파일 자체가 없음** (quota skip). |
| **한도** | EvCharger **일 1,000** 호출 (info+status 공유) · 코드 마진 `SAFETY_MARGIN=50` → 실질 **950**에서 스킵 |

---

## 1. 왜 저녁이 비나

| 사실 | 수치 |
|---|---|
| Lightsail 설정 | **5분** interval · period 10 |
| 틱당 API | 보통 **4~7** (페이지네이션) · 중앙≈5 |
| 24h × 5분 | 288틱 × 5 ≈ **1,440** ≫ 1,000 |
| 7/23 실측 | `calls=950` 도달 후 **16:31~** 전부 `daily_limit_margin` skip |
| 17~23시 CSV | 서버·로컬 **0개** |

→ **API가 죽은 게 아니라, 5분 폴링이 하루 예산을 오전에 다 씀.**

---

## 2. 예산 계산 (틱당 5 call 가정)

| interval | 24h 틱 | 예상 call | 1000 한도 |
|---|---:|---:|---|
| **5분** (현재 서버) | 288 | ~1,440 | ❌ 오후부터 skip |
| **10분** | 144 | ~720 | ✅ 여유 |
| **12분** | 120 | ~600 | ✅ |
| **15분** | 96 | ~480 | ✅ 여유 큼 |

마진 50 유지 시 목표: **일 ≤900 call** 정도.

---

## 3. 전 시간대 채우는 방법 (우선순위)

### P0 — 적용됨 (2026-07-24)

1. **수집은 Lightsail만** — PC에서 `run_loop` 미가동 확인.  
2. 서버 interval **5분 → 10분** 적용·재시작 (`ev-status-loop` ExecStart 확인).  
3. 하루 지나서 pull → 히트맵 0~23 회색 칸 줄었는지 확인.

### P1 — 설정 점검

| 항목 | 권장 |
|---|---|
| `SAFETY_MARGIN` | 50 유지 (한도 초과 리스크 방지). 줄이지 말 것 |
| info 일배치 | status와 **같은 키**면 그 호출도 950에 포함 → 배치 시각·횟수 최소화 |
| traffic 루프 | EvCharger와 **다른 API**면 status 예산과 무관 |

### P2 — 여유 시

- 두 번째 키/계정 (공공 API 정책 허용 시만)  
- 심야만 더 촘게 / 낮만 듬성 (복잡 · 비추, 먼저 10분 고정)

---

## 4. Lightsail (적용 완료)

서버 유닛 현재:

```text
--interval-minutes 10
--period-minutes 10
```

재확인:

```bash
systemctl show ev-status-loop -p ExecStart
systemctl is-active ev-status-loop
```

레포 정본: `infra/deployment/ev-status-loop.service`

---

## 5. 시각 vs 수집

| 목적 | 수단 |
|---|---|
| **지금** 0~23 패턴 보기 | `figures/08_hourly_union_profile.png` (일자 합집합) |
| **앞으로** 날마다 전시간 | API 예산 안에서 24h 루프 (위 P0) |
| 결측 메우기(가짜 fill) | ❌ 하지 않음 |

---

## 6. 한 줄 핸드오프

```text
DA① | EvCharger 일1000 · 5분×24h=예산초과 → 저녁 skip
조치 적용(2026-07-24): PC 루프 OFF · Lightsail interval 10분 · period 10 · active
확인: 익일 pull 후 히트맵 17~23 회색 감소
```
