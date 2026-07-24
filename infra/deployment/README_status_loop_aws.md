# AWS status 루프 (10분) 배포

| | |
|---|---|
| **대상** | 팀 AWS `3.39.251.72` |
| **주기** | interval **10분** · period **10분** |
| **코드** | SANDBOX `run_loop.py` (CSV 스냅샷) |
| **서비스** | `ev-status-loop.service` |

---

## 왜 서버인가

PC 끄면 야간 gap. 서버에 올리면 24h 연속 수집.

## 전제

1. SSH `.pem` (또는 등록된 공개키) — **이 PC에는 아직 키 없음 → Permission denied**
2. 서버 `/opt/ev-safecharge/.env` 에 `DATA_GO_KR_KEY=`
3. **로컬 PC status 루프는 끄기** (한도 이중 소모 금지)
4. collection `scheduler.py` status 도 서버에서 같이 돌리지 말 것

## 한 번에 배포 (키 있는 PC에서)

```bash
export AWS_HOST=3.39.251.72
export AWS_USER=ubuntu          # 또는 ec2-user
export AWS_KEY=~/.ssh/팀키.pem
bash infra/deployment/deploy_status_loop_aws.sh
```

## 수동 (서버 접속 후)

```bash
cd /opt/ev-safecharge
python3 -m venv .venv && .venv/bin/pip install requests python-dotenv pandas
# .env 에 DATA_GO_KR_KEY
sudo cp infra/deployment/ev-status-loop.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ev-status-loop
sudo journalctl -u ev-status-loop -f
```

## 확인

```bash
sudo systemctl status ev-status-loop
ls apps/data-pipeline/evaluation/personal/experiments/SANDBOX_20260717_status_periodic_collection/data/snapshots/ | tail
```

스냅샷을 PC로 가져올 때:

```bash
scp -i $AWS_KEY -r ubuntu@3.39.251.72:/opt/ev-safecharge/apps/data-pipeline/evaluation/personal/experiments/SANDBOX_20260717_status_periodic_collection/data/snapshots ./snapshots_from_aws
```

```
DA➀ | aws status loop 10m | 2026-07-22
```
