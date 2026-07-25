# Lightsail / AWS — status 10분 + 소통 15분 배포

| | |
|---|---|
| **대상** | Lightsail `우분투-1` · `3.36.50.99` (1GB) |
| **status** | interval **10분** · period **10분** · `ev-status-loop.service` (5분이면 일 1000 한도로 저녁 skip) |
| **소통** | interval **15분** · `ev-traffic-loop.service` |
| **관광지↔충전 이용** | **일 1회** 04:30 KST · `ev-tour-usage-daily.timer` (배치 · 수집 루프 아님) |
| **저장** | `/opt/ev-safecharge/docs/data/loops/loop1/` · `loop3/` · 분석은 `docs/data/analysis/tour_charger_usage/` |
| **키** | `/opt/ev-safecharge/.env` (`DATA_GO_KR_KEY`) |
| **전시간대** | [`docs/보고/전시간대_수집_API한도_20260724.md`](../../docs/보고/전시간대_수집_API한도_20260724.md) |

PC 끄면 야간 gap → 서버 24h 수집. **로컬 status/소통 루프는 끄기** (한도 이중 소모).

배포 필수: `collection/daily_exports.py` + `ev_charger_info.py`, pip에 `matplotlib` 포함.

## 배포 (키 있는 PC)

```powershell
# PowerShell — 레포 루트에서
$env:AWS_HOST = "3.36.50.99"
$env:AWS_USER = "ubuntu"
$env:AWS_KEY  = "$env:USERPROFILE\.ssh\LightsailDefaultKey-ap-northeast-2.pem"
# Git Bash 또는 WSL:
bash infra/deployment/deploy_loops_lightsail.sh
```

## PC로 CSV 가져오기

```powershell
# PowerShell — $host 는 예약 변수 → $awsHost 사용
$key = "$env:USERPROFILE\.ssh\LightsailDefaultKey-ap-northeast-2.pem"
$awsHost = "3.36.50.99"
scp -i $key -r "ubuntu@${awsHost}:/opt/ev-safecharge/docs/data/loops/loop1" ./loop1_from_server
scp -i $key -r "ubuntu@${awsHost}:/opt/ev-safecharge/docs/data/loops/loop3" ./loop3_from_server
```

최근 pull: `docs/data/loops/_archive/from_lightsail_20260723_210340/` (2026-07-23 · snap 220 → live 합침)

## 로그

```bash
sudo journalctl -u ev-status-loop -f
sudo journalctl -u ev-traffic-loop -f
```

```
DA➀ | lightsail status 5m + traffic 15m | 2026-07-22
```
