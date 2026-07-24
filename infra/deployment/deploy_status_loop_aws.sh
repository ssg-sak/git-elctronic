#!/usr/bin/env bash
# Deploy SANDBOX status loop (10 min) to team AWS.
# Usage (from repo root, on your PC with the .pem):
#   export AWS_HOST=3.39.251.72
#   export AWS_USER=ubuntu
#   export AWS_KEY=~/.ssh/ev-safecharge.pem
#   bash infra/deployment/deploy_status_loop_aws.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HOST="${AWS_HOST:-3.39.251.72}"
USER="${AWS_USER:-ubuntu}"
KEY="${AWS_KEY:-}"
REMOTE_DIR="${AWS_REMOTE_DIR:-/opt/ev-safecharge}"

if [[ -z "$KEY" || ! -f "${KEY/#\~/$HOME}" ]]; then
  echo "Set AWS_KEY to your .pem path (readable). Example:"
  echo "  export AWS_KEY=~/.ssh/your-key.pem"
  exit 1
fi
KEY="${KEY/#\~/$HOME}"
SSH=(ssh -i "$KEY" -o StrictHostKeyChecking=accept-new "${USER}@${HOST}")
SCP=(scp -i "$KEY" -o StrictHostKeyChecking=accept-new)

echo "==> remote prep ${USER}@${HOST}:${REMOTE_DIR}"
"${SSH[@]}" "sudo mkdir -p ${REMOTE_DIR} && sudo chown ${USER}:${USER} ${REMOTE_DIR}"

echo "==> rsync repo (no .git large caches optional)"
rsync -az --delete \
  --exclude '.git' \
  --exclude '**/__pycache__' \
  --exclude '**/.venv' \
  --exclude 'node_modules' \
  -e "ssh -i ${KEY} -o StrictHostKeyChecking=accept-new" \
  "${ROOT}/" "${USER}@${HOST}:${REMOTE_DIR}/"

echo "==> ensure .env on server (DATA_GO_KR_KEY required)"
"${SSH[@]}" "test -f ${REMOTE_DIR}/.env || (echo 'MISSING ${REMOTE_DIR}/.env — copy from local once' && exit 1)"

echo "==> venv + deps"
"${SSH[@]}" "cd ${REMOTE_DIR} && python3 -m venv .venv && .venv/bin/pip install -q -U pip && .venv/bin/pip install -q requests python-dotenv pandas"

echo "==> install systemd unit"
"${SSH[@]}" "sudo cp ${REMOTE_DIR}/infra/deployment/ev-status-loop.service /etc/systemd/system/ev-status-loop.service && sudo systemctl daemon-reload && sudo systemctl enable --now ev-status-loop.service && sudo systemctl status ev-status-loop.service --no-pager"

echo "==> done. logs: sudo journalctl -u ev-status-loop -f"
echo "    snapshots: ${REMOTE_DIR}/apps/data-pipeline/evaluation/personal/experiments/SANDBOX_20260717_status_periodic_collection/data/snapshots/"
