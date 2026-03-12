#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AGENT_DIR="${ROOT_DIR}/agent"
LOG_DIR="${ROOT_DIR}/log"
AGENT_PORT="${AGENT_PORT:-8000}"
RUN_ID="${OPENNOVEL_RUN_ID:-$(date +%Y%m%d-%H%M%S)}"
AGENT_PID_FILE="${LOG_DIR}/agent.pid"
mkdir -p "${LOG_DIR}"

if [[ ! -x "${AGENT_DIR}/.venv/bin/uvicorn" ]]; then
  echo "Missing agent virtualenv at ${AGENT_DIR}/.venv"
  echo "Install it first, for example: uv venv agent/.venv && uv pip install --python agent/.venv/bin/python -e agent"
  exit 1
fi

cleanup() {
  local exit_code=$?
  if [[ -n "${TAIL_PID:-}" ]] && kill -0 "${TAIL_PID}" 2>/dev/null; then
    kill "${TAIL_PID}" 2>/dev/null || true
  fi
  if [[ -n "${AGENT_PID:-}" ]] && kill -0 "${AGENT_PID}" 2>/dev/null; then
    kill "${AGENT_PID}" 2>/dev/null || true
  fi
  rm -f "${AGENT_PID_FILE}"
  wait "${AGENT_PID:-}" 2>/dev/null || true
  exit "${exit_code}"
}

trap cleanup EXIT INT TERM

echo "Starting OpenNovel agent in debug mode"
echo "Agent:   http://127.0.0.1:${AGENT_PORT}"
echo "Run ID:  ${RUN_ID}"
echo "Logs:    ${LOG_DIR}/agent.debug.${RUN_ID}.log"
echo "Combined:${LOG_DIR}/combined/run-${RUN_ID}.jsonl"

cd "${ROOT_DIR}"
OPENNOVEL_RUN_ID="${RUN_ID}" "${AGENT_DIR}/.venv/bin/uvicorn" app.main:app \
  --app-dir agent \
  --host 127.0.0.1 \
  --port "${AGENT_PORT}" \
  --reload \
  > "${LOG_DIR}/agent.debug.${RUN_ID}.log" 2>&1 &
AGENT_PID=$!
printf '%s\n' "${AGENT_PID}" > "${AGENT_PID_FILE}"

tail -f "${LOG_DIR}/agent.debug.${RUN_ID}.log" &
TAIL_PID=$!

wait "${AGENT_PID}"
