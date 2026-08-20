#!/usr/bin/env bash
# Deploy status (5m) + Daegu traffic (15m) to Lightsail / AWS.
# From repo root:
#   export AWS_HOST=3.36.50.99
#   export AWS_USER=ubuntu
#   export AWS_KEY=~/.ssh/LightsailDefaultKey-ap-northeast-2.pem
#   bash infra/deployment/deploy_loops_lightsail.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HOST="${AWS_HOST:-3.36.50.99}"
USER="${AWS_USER:-ubuntu}"
KEY="${AWS_KEY:-}"
REMOTE_DIR="${AWS_REMOTE_DIR:-/opt/ev-safecharge}"

if [[ -z "$KEY" || ! -f "${KEY/#\~/$HOME}" ]]; then
  echo "Set AWS_KEY to your .pem path"
  exit 1
fi
KEY="${KEY/#\~/$HOME}"
SSH=(ssh -i "$KEY" -o StrictHostKeyChecking=accept-new "${USER}@${HOST}")
SCP=(scp -i "$KEY" -o StrictHostKeyChecking=accept-new)

if [[ ! -f "${ROOT}/.env" ]]; then
  echo "Missing ${ROOT}/.env (DATA_GO_KR_KEY required)"
  exit 1
fi

echo "==> remote prep"
"${SSH[@]}" "sudo mkdir -p ${REMOTE_DIR} && sudo chown ${USER}:${USER} ${REMOTE_DIR}"

echo "==> sync lean tree (no big CSVs / .git / venv)"
if command -v rsync >/dev/null 2>&1; then
  rsync -az --delete \
    --exclude '.git' \
    --exclude '**/__pycache__' \
    --exclude '**/.venv' \
    --exclude 'node_modules' \
    --exclude 'apps/data-pipeline/evaluation/results' \
    --exclude 'apps/data-pipeline/evaluation/personal/experiments/SANDBOX_*/data' \
    --exclude 'docs/data/extracted' \
    --exclude 'docs/data/loops/loop1/snapshots' \
    --exclude 'docs/data/loops/loop1/daily' \
    --exclude 'docs/data/loops/loop2' \
    --exclude 'docs/data/loops/loop3/*.csv' \
    --exclude 'docs/data/loops/loop3/*.json' \
    --exclude 'apps/web' \
    --exclude 'apps/api' \
    --exclude 'packages' \
    -e "ssh -i ${KEY} -o StrictHostKeyChecking=accept-new" \
    "${ROOT}/" "${USER}@${HOST}:${REMOTE_DIR}/"
else
  echo "rsync not found — using tar+scp"
  TMP=$(mktemp -d)
  tar -C "${ROOT}" -czf "${TMP}/ev.tgz" \
    --exclude='.git' --exclude='**/__pycache__' --exclude='**/.venv' \
    --exclude='node_modules' --exclude='apps/web' --exclude='apps/api' \
    --exclude='packages' --exclude='apps/data-pipeline/evaluation/results' \
    --exclude='docs/data/extracted' \
    apps/data-pipeline infra/deployment docs/data/loops AGENTS.md .env.example 2>/dev/null || true
  # always include required dirs
  tar -C "${ROOT}" -czf "${TMP}/ev.tgz" \
    apps/data-pipeline/loop_paths.py \
    apps/data-pipeline/processing \
    apps/data-pipeline/collection/daily_exports.py \
    apps/data-pipeline/collection/ev_charger_info.py \
    apps/data-pipeline/evaluation/personal/experiments/SANDBOX_20260717_status_periodic_collection/src \
    infra/deployment \
    docs/data/loops
  "${SCP[@]}" "${TMP}/ev.tgz" "${USER}@${HOST}:/tmp/ev.tgz"
  "${SSH[@]}" "mkdir -p ${REMOTE_DIR} && tar -C ${REMOTE_DIR} -xzf /tmp/ev.tgz && rm /tmp/ev.tgz"
  rm -rf "${TMP}"
fi

echo "==> copy .env"
"${SCP[@]}" "${ROOT}/.env" "${USER}@${HOST}:${REMOTE_DIR}/.env"
"${SSH[@]}" "chmod 600 ${REMOTE_DIR}/.env && mkdir -p ${REMOTE_DIR}/docs/data/loops/loop1/snapshots ${REMOTE_DIR}/docs/data/loops/loop1/logs ${REMOTE_DIR}/docs/data/loops/loop3 ${REMOTE_DIR}/docs/data/extracted/daily"

echo "==> venv + deps (python3-venv required on Ubuntu)"
"${SSH[@]}" "sudo apt-get install -y -qq python3-venv >/dev/null 2>&1 || true; cd ${REMOTE_DIR} && python3 -m venv .venv && .venv/bin/pip install -q -U pip && .venv/bin/pip install -q 'requests>=2.28' 'python-dotenv>=1.0' 'pandas>=2.0' 'matplotlib>=3.7'"

echo "==> systemd units"
"${SSH[@]}" "sudo cp ${REMOTE_DIR}/infra/deployment/ev-status-loop.service /etc/systemd/system/ && sudo cp ${REMOTE_DIR}/infra/deployment/ev-traffic-loop.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now ev-status-loop.service ev-traffic-loop.service && sudo systemctl restart ev-status-loop.service ev-traffic-loop.service && sudo systemctl --no-pager --full status ev-status-loop.service ev-traffic-loop.service | head -40"

echo "==> done"
echo "  status logs:  sudo journalctl -u ev-status-loop -f"
echo "  traffic logs: sudo journalctl -u ev-traffic-loop -f"
echo "  loop1: ${REMOTE_DIR}/docs/data/loops/loop1/snapshots/"
echo "  loop3: ${REMOTE_DIR}/docs/data/loops/loop3/"
