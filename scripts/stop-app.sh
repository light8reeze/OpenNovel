#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${ROOT_DIR}/log"
AGENT_PID_FILE="${LOG_DIR}/agent.pid"
BACKEND_PID_FILE="${LOG_DIR}/backend.pid"

stop_pid_file() {
  local label=$1
  local pid_file=$2

  if [[ ! -f "${pid_file}" ]]; then
    echo "${label}: pid file not found"
    return
  fi

  local pid
  pid="$(cat "${pid_file}")"
  if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
    kill "${pid}"
    echo "${label}: stopped pid ${pid}"
  else
    echo "${label}: process not running"
  fi

  rm -f "${pid_file}"
}

stop_pid_file "agent" "${AGENT_PID_FILE}"
stop_pid_file "backend" "${BACKEND_PID_FILE}"
