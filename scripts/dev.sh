#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_HOST="${CTM_BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${CTM_BACKEND_PORT:-8000}"
FRONTEND_HOST="${CTM_FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${CTM_FRONTEND_PORT:-3000}"
BACKEND_HEALTH_URL="http://${BACKEND_HOST}:${BACKEND_PORT}/api/v1/health"

export CTM_API_KEY="${CTM_API_KEY:-local-dev-api-key}"
export CTM_FRONTEND_API_BASE_URL="${CTM_FRONTEND_API_BASE_URL:-http://${BACKEND_HOST}:${BACKEND_PORT}/api/v1}"
export CTM_FRONTEND_API_KEY="${CTM_FRONTEND_API_KEY:-$CTM_API_KEY}"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

require_path() {
  if [[ ! -e "$1" ]]; then
    echo "Missing required path: $1" >&2
    exit 1
  fi
}

port_is_in_use() {
  lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
}

backend_is_ctm() {
  local response

  if ! response="$(curl --silent --show-error --fail --max-time 2 "${BACKEND_HEALTH_URL}" 2>/dev/null)"; then
    return 1
  fi

  [[ "${response}" == *"pipeline_version"* && "${response}" == *"status"* ]]
}

ensure_backend_port() {
  if ! port_is_in_use "${BACKEND_PORT}"; then
    return 0
  fi

  if backend_is_ctm; then
    return 0
  fi

  echo "Backend port ${BACKEND_PORT} is already in use by a non-CTM process." >&2
  echo "Stop the existing process or set CTM_BACKEND_PORT and CTM_FRONTEND_API_BASE_URL to a free port." >&2
  exit 1
}

ensure_frontend_port() {
  if ! port_is_in_use "${FRONTEND_PORT}"; then
    return 0
  fi

  echo "Frontend port ${FRONTEND_PORT} is already in use." >&2
  echo "Stop the existing process or set CTM_FRONTEND_PORT to a free port." >&2
  exit 1
}

cleanup() {
  local exit_code="${1:-$?}"
  trap - EXIT INT TERM

  if [[ -n "${BACKEND_PID:-}" ]]; then
    kill "${BACKEND_PID}" 2>/dev/null || true
  fi
  if [[ -n "${FRONTEND_PID:-}" ]]; then
    kill "${FRONTEND_PID}" 2>/dev/null || true
  fi

  wait "${BACKEND_PID:-}" 2>/dev/null || true
  wait "${FRONTEND_PID:-}" 2>/dev/null || true
  exit "${exit_code}"
}

trap 'cleanup $?' EXIT INT TERM

require_command alembic
require_command uvicorn
require_command npm
require_command curl
require_command lsof
require_path "${ROOT_DIR}/frontend/package.json"
require_path "${ROOT_DIR}/frontend/node_modules"

ensure_backend_port
ensure_frontend_port

if backend_is_ctm; then
  echo "Reusing existing CTM backend on ${BACKEND_HEALTH_URL}"
  REUSE_BACKEND=1
  BACKEND_PID=""
else
  REUSE_BACKEND=0
fi

if [[ "${REUSE_BACKEND}" == "0" && "${CTM_SKIP_MIGRATIONS:-0}" != "1" ]]; then
  ALEMBIC_LOG="$(mktemp "${TMPDIR:-/tmp}/ctm-alembic.XXXXXX")"
  echo "Running database migrations..."
  if ! (
    cd "${ROOT_DIR}"
    alembic upgrade head
  ) >"${ALEMBIC_LOG}" 2>&1; then
    echo "Database migration failed." >&2
    echo "Check CTM_DATABASE_URL and make sure PostgreSQL is reachable from this shell." >&2
    echo "If you already have a healthy CTM backend running, start the launcher with CTM_SKIP_MIGRATIONS=1." >&2
    echo "Last Alembic output:" >&2
    tail -n 12 "${ALEMBIC_LOG}" >&2 || true
    echo "Full Alembic log: ${ALEMBIC_LOG}" >&2
    exit 1
  fi
  rm -f "${ALEMBIC_LOG}"
fi

if [[ "${REUSE_BACKEND}" == "0" ]]; then
  echo "Starting backend: http://${BACKEND_HOST}:${BACKEND_PORT}"
  (
    cd "${ROOT_DIR}"
    uvicorn app.main:app --reload --host "${BACKEND_HOST}" --port "${BACKEND_PORT}"
  ) &
  BACKEND_PID=$!
fi

echo "Starting frontend: http://${FRONTEND_HOST}:${FRONTEND_PORT}"
(
  cd "${ROOT_DIR}/frontend"
  npm run dev -- --hostname "${FRONTEND_HOST}" --port "${FRONTEND_PORT}"
) &
FRONTEND_PID=$!

echo "Frontend and backend are starting."
echo "Frontend: http://${FRONTEND_HOST}:${FRONTEND_PORT}"
echo "Backend health: ${BACKEND_HEALTH_URL}"

while true; do
  if [[ -n "${BACKEND_PID:-}" ]] && ! kill -0 "${BACKEND_PID}" 2>/dev/null; then
    wait "${BACKEND_PID}"
    exit $?
  fi

  if ! kill -0 "${FRONTEND_PID}" 2>/dev/null; then
    wait "${FRONTEND_PID}"
    exit $?
  fi

  sleep 1
done
