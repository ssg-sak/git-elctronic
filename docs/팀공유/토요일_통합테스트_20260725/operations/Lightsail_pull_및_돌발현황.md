# Lightsail 루프 pull · 돌발 현황 (DA①)

| | |
|---|---|
| **작성** | 2026-07-24 |
| **서버** | `3.36.50.99` · `/opt/ev-safecharge` (1GB · 구 `54.180.135.242` / `52.79.224.112`) |
| **원칙** | **서버만 수집** · PC 루프 OFF · 가끔 pull |

---

## 0. 운영 안정화 메모 (2026-07-25)

### 현재 확정 상태

| 항목 | 상태 |
|---|---|
| 운영 인스턴스 | Lightsail `우분투-1` · **1GB RAM** · `3.36.50.99` |
| 기존 512MB 인스턴스 | **사용자 삭제 완료** |
| Swap | **2GB `/swapfile`** · `/etc/fstab` 등록 → 재부팅 후에도 유지 |
| status | `ev-status-loop` · 10분 |
| traffic | `ev-traffic-loop` · 15분 |
| 저장공간 | 40GB 플랜 · loop CSV 수 주 보관 가능 |
| 공공데이터포털 키 | `DATA_GO_KR_KEY` 방식 — **IP 등록 작업 없음** |

기존 512MB 서버에서는 Python status 수집이 약 220MB까지 올라가며 OOM으로 종료됐다.
1GB + 2GB swap은 해당 문제의 운영 완화책이다. CSV 누적량은 디스크 문제이지 OOM의 직접 원인이 아니다.

### 매일 확인할 것

```bash
# SSH 접속 후
systemctl is-active ev-status-loop ev-traffic-loop
free -h
sudo journalctl -u ev-status-loop -n 20 --no-pager
sudo journalctl -u ev-traffic-loop -n 20 --no-pager
```

정상 기준: 두 서비스가 모두 `active`, 로그에 최근 성공 수집 JSON이 있고
`Out of memory` / `Killed process` 반복이 없어야 한다.

### pull · 보관 규칙

```powershell
# PC 레포 루트
powershell -ExecutionPolicy Bypass -File scripts/pull_lightsail_loops.ps1
```

- 서버는 현재 flat CSV로 수집해도 됨.
- PC pull 시 자동으로 **일자별** live 폴더에 합쳐짐.
  - status: `loop1/snapshots/YYYYMMDD/`
  - 소통·대구돌발: `loop3/YYYYMMDD/`
- `*_latest.csv`는 loop3 루트에 남긴다.
- PC 정본 + `from_lightsail_*` pull archive가 확보된 뒤에만 서버의 오래된 CSV를 정리한다.
  최근 2일·`*_latest.csv`·로그는 남긴다.

### IP 변경·재부팅 체크리스트

- [ ] Lightsail **고정 IP** 연결 여부 확인 (미연결이면 Stop/Start 뒤 IP 변경 가능)
- [ ] IP가 바뀌면 `scripts/pull_lightsail_loops.ps1` 기본 `AwsHost` 갱신
- [ ] IP가 바뀌면 `infra/deployment/README_loops_lightsail.md` 갱신
- [ ] `ssh -i <key> ubuntu@<IP> "hostname; date"` 성공 확인
- [ ] 두 systemd 서비스 `active` 확인
- [ ] 한 번 pull하여 PC에 최신 데이터가 들어오는지 확인

> 새 인스턴스로 교체할 때는 `.env`, `.venv`, `/opt/ev-safecharge`, systemd 서비스가
> 준비됐는지 확인하고, 이전 인스턴스는 새 서버 수집 성공 후 삭제한다.

---

## 1. pull 하는 법 (기록용)

```powershell
# 레포 루트 (Windows PowerShell)
powershell -ExecutionPolicy Bypass -File scripts/pull_lightsail_loops.ps1
```

| 결과 | 위치 |
|---|---|
| 원본 보관 | `docs/data/loops/_archive/from_lightsail_YYYYMMDD_HHMMSS/` |
| live 합침 | `docs/data/loops/loop1/` · `loop3/` (새 파일만 추가) |
| 최신 포인터 | `_archive/from_lightsail_latest.txt` · `from_lightsail_latest_PULL_META.json` |
| 이력 표 | `_archive/PULL_LOG.md` |

권장 주기: **하루 1~2회** (분석·D1 전). 매 틱마다 안 해도 됨.

pull 직후 로컬 파일 신선도만 확인하려면 다음을 실행한다. 이 검사는 API 호출·D1 재생성을 하지 않는다.

```powershell
python apps/data-pipeline/processing/analysis/check_collection_health.py
```

---

## 2. 지금 돌발은 실시간인가?

| 소스 | 서버 루프 | 실시간? | 비고 |
|---|---|---|---|
| **대구 dgincident** (loop3와 같이) | ✅ `ev-traffic-loop` 15분 | **호출은 함** | 최근 스냅 **0건**(헤더만) — API ok, 진행 중 돌발 없음 |
| **UTIC 돌발** (loop2) | ❌ 서버에 서비스/폴더 없음 | **아니오** | PC에서 7/22까지 돌다 중단 · D1 조인은 그 시점 CSV |

정리: **소통(linkspeed)은 실시간. 돌발은 “받고는 있으나(대구) 지금 사건이 거의 없고, UTIC는 서버에서 안 돌고 있음”.**

> **2026-07-25 16:20** — 새 UTIC 키로 PC에서 `run_utic_loop.py --once`를 1회 실행했다.
> 전국 114건 중 대구 7건을 저장했고, 충전소 266개가 1km 내 돌발과 결합됐다.
> 서버 반복 루프는 등록하지 않았으며, 현재 D1에는 다음 재빌드 전까지 직전 UTIC 조인값이 남는다.

---

## 3. 돌발 분석할 만한가?

| 할 만함 | 비고 |
|---|---|
| ✅ **소 근처 거리 플래그** | 이미 D1 `nearest_incident_m` (UTIC 조인 ~435소) — 경고·감점 보조 |
| ✅ **유형 분포** | 공사 vs 사고 (건수 적을 때 리포트용) |
| ✅ **혼잡과 겹침** | 돌발 있는 시각 vs 도시 정체% (건수 쌓이면) |
| ❌ **단독 ML/시계열** | 건수가 너무 듬성 (하루 0~수십) — 학습 라벨로 약함 |

**우선순위:** UTIC를 서버에 다시 올릴지 팀 합의 → 그전엔 dgincident 0건이어도 loop3는 유지(소통이 본진).

---

## 4. 관련

- 배포: [`infra/deployment/README_loops_lightsail.md`](../../infra/deployment/README_loops_lightsail.md)
- 소통 보고: [`../품질보고/교통소통_데이터_보고.md`](../품질보고/교통소통_데이터_보고.md)
- UTIC 준수: [`../API/UTIC_개방데이터_준수사항.md`](../API/UTIC_개방데이터_준수사항.md)

```
DA① | lightsail pull + incident status | 2026-07-24
```


## 5. 오프라인 분석 산출

- 팀공유: [`../../팀공유/돌발_UTIC_분석_20260724/`](../../팀공유/돌발_UTIC_분석_20260724/)
- 재실행: `python apps/data-pipeline/processing/analysis/analyze_utic_incidents.py`
