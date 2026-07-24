# DBeaver · 로컬 테스트 DB (status 패널)

| | |
|---|---|
| **담당** | AI·데이터 ① |
| **작성** | 2026-07-22 |
| **한 줄** | **완전 테스트용.** 운영·서버·루프에 붙이지 않는다. 필요할 때만 수동으로 본다. |

> **돌리지 말 것:** status 루프·AWS·Render·자동 적재와 **연결하지 않음**.  
> 정본은 계속 SANDBOX `snapshots/` CSV. DB는 DBeaver 구경용 복제본일 뿐.

---

## 접속 (DBeaver) — 수동일 때만

| 항목 | 값 |
|---|---|
| Host | `localhost` |
| Port | `5432` |
| Database | `ev_safecharge` |
| User | `postgres` |
| Password | 루트 `.env`의 `POSTGRES_PASSWORD` |

---

## 적재 (원할 때만 · 기본 차단)

실수로 돌리지 않도록 `ALLOW_TEST_DB_LOAD=1` 이 없으면 스크립트가 종료된다.

```bash
pip install -r apps/data-pipeline/processing/requirements-pg.txt
set ALLOW_TEST_DB_LOAD=1
python apps/data-pipeline/processing/db/load_status_panel_to_pg.py
```

### 충전기 기본정보만 (info)

```bash
set ALLOW_TEST_DB_LOAD=1
python apps/data-pipeline/processing/db/load_charger_info_to_pg.py
```

| 테이블 | 내용 |
|---|---|
| `ev_charger_info` | 최신 `daegu_charger_info_*` (getChargerInfo) · ~25k행 |

### 운영시간만 (useTime 필터)

```bash
set ALLOW_TEST_DB_LOAD=1
python apps/data-pipeline/processing/db/load_charger_hours_to_pg.py
```

| 테이블 | 내용 |
|---|---|
| `ev_charger_hours` | 496개소 · `useTime` + `is_operating_now` |

스키마: [`apps/data-pipeline/processing/sql/init_status_test_schema.sql`](../../apps/data-pipeline/processing/sql/init_status_test_schema.sql)

| 테이블 | 내용 |
|---|---|
| `meta_collection_schedule` | 스케줄 메모 |
| `charger_status_tick` | index.csv 복제 |
| `station_feature_panel` | D2 패널 복제 |

```
DA➀ | test db only — do not run in ops | 2026-07-22
```
