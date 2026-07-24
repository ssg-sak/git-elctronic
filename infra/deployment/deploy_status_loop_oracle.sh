#!/usr/bin/env bash
# Deploy SANDBOX status loop (10 min) to Oracle Cloud Always Free VM.
#   export ORACLE_HOST=x.x.x.x
#   export ORACLE_USER=ubuntu   # or opc
#   export ORACLE_KEY=~/.ssh/oracle.pem
#   bash infra/deployment/deploy_status_loop_oracle.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HOST="${ORACLE_HOST:-}"
USER="${ORACLE_USER:-ubuntu}"
KEY="${ORACLE_KEY:-}"
REMOTE_DIR="${ORACLE_REMOTE_DIR:-/opt/ev-safecharge}"

if [[ -z "$HOST" ]]; then
  echo "Set ORACLE_HOST to the VM public IP"
  exit 1
fi
if [[ -z "$KEY" || ! -f "${KEY/#\~/$HOME}" ]]; then
  echo "Set ORACLE_KEY to your private key path"
  exit 1
fi
KEY="${KEY/#\~/$HOME}"
SSH=(ssh -i "$KEY" -o StrictHostKeyChecking=accept-new "${USER}@${HOST}")

echo "==> prep ${USER}@${HOST}:${REMOTE_DIR}"
"${SSH[@]}" "sudo mkdir -p ${REMOTE_DIR} && sudo chown ${USER}:${USER} ${REMOTE_DIR}"

echo "==> rsync"
rsync -az --delete \
  --exclude '.git' \
  --exclude '**/__pycache__' \
  --exclude '**/.venv' \
  --exclude 'node_modules' \
  -e "ssh -i ${KEY} -o StrictHostKeyChecking=accept-new" \
  "${ROOT}/" "${USER}@${HOST}:${REMOTE_DIR}/"

echo "==> require .env with DATA_GO_KR_KEY"
"${SSH[@]}" "test -f ${REMOTE_DIR}/.env || (echo 'Put .env on server first' && exit 1)"

echo "==> patch systemd User=${USER}"
"${SSH[@]}" "sed 's/^User=.*/User=${USER}/' ${REMOTE_DIR}/infra/deployment/ev-status-loop.service | sudo tee /etc/systemd/system/ev-status-loop.service > /dev/null"

echo "==> venv"
"${SSH[@]}" "cd ${REMOTE_DIR} && python3 -m venv .venv && .venv/bin/pip install -q -U pip && .venv/bin/pip install -q requests python-dotenv pandas"

echo "==> enable service"
"${SSH[@]}" "sudo systemctl daemon-reload && sudo systemctl enable --now ev-status-loop.service && sudo systemctl status ev-status-loop.service --no-pager"

echo "==> done. journalctl -u ev-status-loop -f"
