# Oracle Cloud Always Free — status 10분 루프

| | |
|---|---|
| **목적** | PC 꺼도 EvCharger status 스냅샷 계속 쌓기 |
| **비용** | Always Free (가입 시 카드 등록은 보통 필요 · 과금 안 되게 Free tier만) |
| **주기** | interval **10분** · period **10분** |

팀 공용 서버가 없을 때 **임시 상시기**용. 나중에 팀 서버 생기면 이사.

---

## 0. 가입 전 팁 (짜증 줄이기)

1. https://www.oracle.com/cloud/free/ 에서 **Always Free** 가입  
2. **Home Region**은 나중에 못 바꿈 → `Japan Central (Osaka)` / `Japan East (Tokyo)` / `South Korea Central (Seoul)` 중 **용량 남는 곳** (Seoul이 자주 꽉 참 → Osaka·Tokyo 많이 씀)  
3. 카드 등록 후 **승인 메일** 올 때까지 대기 (몇 시간~하루)  
4. 콘솔 로그인 → **Compute → Instances → Create**

용량 없음(Out of capacity) 뜨면:
- 다른 AD(가용 영역) 재시도  
- Shape을 `VM.Standard.A1.Flex` (Ampere ARM) 로  
- 또는 다른 Home Region으로 **새 계정**(최후)

---

## 1. 인스턴스 만들기 (추천)

| 항목 | 추천 |
|---|---|
| Image | **Ubuntu 22.04** |
| Shape | **VM.Standard.A1.Flex** (Ampere) · OCPU 2 · RAM 12GB 이내 Always Free |
| Boot | 50GB |
| SSH | 본인 공개키 등록 · `.pem`/`.key` 보관 |
| VCN | 기본 생성 · **Egress(아웃바운드) 허용** (API 호출용). status 루프는 **인바운드 포트 열 필요 없음** |

생성 후 **Public IP** 메모.

```bash
ssh -i 네키.pem ubuntu@<PUBLIC_IP>
# 이미지가 oracle 기본이면 유저가 ubuntu 가 아니라 opc 일 수 있음 → opc 로 시도
```

---

## 2. 서버에 코드·루프

PC(깃 있는 곳)에서:

```bash
export ORACLE_HOST=<PUBLIC_IP>
export ORACLE_USER=ubuntu          # 또는 opc
export ORACLE_KEY=~/.ssh/oracle.pem
bash infra/deployment/deploy_status_loop_oracle.sh
```

또는 서버에서 수동:

```bash
sudo apt update && sudo apt install -y python3-venv python3-pip git
sudo mkdir -p /opt/ev-safecharge && sudo chown $USER:$USER /opt/ev-safecharge
# git clone 또는 scp 로 레포 복사
cd /opt/ev-safecharge
python3 -m venv .venv
.venv/bin/pip install requests python-dotenv pandas
nano .env   # DATA_GO_KR_KEY=... 만 있으면 됨 (키 커밋 금지)

sudo cp infra/deployment/ev-status-loop.service /etc/systemd/system/
# WorkingDirectory·User 가 ubuntu/opc 와 맞는지 확인
sudo systemctl daemon-reload
sudo systemctl enable --now ev-status-loop
sudo journalctl -u ev-status-loop -f
```

스냅샷 위치:

`/opt/ev-safecharge/apps/data-pipeline/evaluation/personal/experiments/SANDBOX_20260717_status_periodic_collection/data/snapshots/`

PC로 받아오기:

```bash
scp -i $ORACLE_KEY -r ${ORACLE_USER}@${ORACLE_HOST}:/opt/ev-safecharge/apps/data-pipeline/evaluation/personal/experiments/SANDBOX_20260717_status_periodic_collection/data/snapshots ./snapshots_from_oracle
```

---

## 3. 꼭 지킬 것

- **로컬 PC status 루프는 끄기** (일 1,000콜 공유)
- 테스트 DB(`ev_safecharge` Postgres)는 **연결하지 않음**
- 키는 서버 `.env`만 · 깃에 넣지 말 것
- Always Free 한도·유휴 정책은 콘솔에서 가끔 확인

---

## 가입 체크리스트

- [ ] 계정 생성 · Home Region 선택  
- [ ] 메일 인증 · 카드  
- [ ] Ubuntu + A1.Flex 인스턴스  
- [ ] SSH 접속  
- [ ] `.env` + `ev-status-loop` enable  
- [ ] 10분 뒤 snapshots 새 파일 확인  
- [ ] 로컬 루프 OFF  

막히면 화면(에러 문구)만 보내면 됨.

```
DA➀ | oracle free status loop guide | 2026-07-22
```
