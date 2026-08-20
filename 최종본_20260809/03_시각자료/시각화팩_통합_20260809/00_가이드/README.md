# 주차장·주차요금 관련 데이터 추출 (20260803)

| 항목 | 내용 |
|---|---|
| **작성** | AI·데이터 ① |
| **한 줄** | “약 2만 건”은 **충전기 parkingFree(Y/N) ~2.5만**에 가깝고, **주차장 요금 금액**은 Team5 **~1.7천 곳**이다. |

---

## A. 충전기 주차 무료 여부 (`parkingFree`) — ~25,433행

| 항목 | 값 |
|---|---:|
| 충전기 행 | **25,433** |
| parkingFree=Y | **16,172** |
| parkingFree=N | **9,257** |
| 충전소 수 | **4,212** |

- 원천: EvCharger `getChargerInfo` · `docs/data/extracted/charger/info/daegu_charger_info_latest.csv`
- 파일: `charger_parkingFree_flags.csv` · `charger_parkingFree_by_station.csv`
- **금액(원) 없음** — 무료/유료 플래그만

---

## B. Team5 주차장 요금 필드 — ~1,767곳

| 필드 | non-null |
|---|---:|
| 유료/무료 (`crg_levy_se_nm`) | 1659 |
| 일반 1시간 (`gnrl_one_hr_crg`) | 71 |
| 일반 1일 (`gnrl_one_day_crg`) | 237 |
| 최초요금 (`gnrl_frst_crg`) | 160 |
| 결제수단 (`stlm_mthd`) | 228 |

- 원천: `docs/data/extracted/parking/team5_full_snapshot_20260803_152354/parking_lot_info.csv`
- 파일: `team5_parking_lot_fees.csv` (flat + `raw_item.prkOperInfo` 펼침)
- 1시간 요금이 채워진 곳은 **소수** — 유료/무료 구분 위주

---

## 헷갈리기 쉬운 것

| 데이터 | 행수 | 요금? |
|---|---:|---|
| charger `parkingFree` | ~25k | 플래그만 |
| Team5 lot fees | ~1.7k | 금액·유무료 (부분) |
| realtime history | ~20k | **아님** (점유 이력) |
| extracted/fee (한전 등) | 소량 | **충전 요금** (주차 아님) |

상세: `docs/data/analysis/parking_fee_20260803`

```
DA① | parking fee extract | 20260803
```
