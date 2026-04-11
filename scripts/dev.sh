#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_HOST="${CTM_BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${CTM_BACKEND_PORT:-8000}"
FRONTEND_HOST="${CTM_FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${CTM_FRONTEND_PORT:-3000}"

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
require_path "${ROOT_DIR}/frontend/package.json"
require_path "${ROOT_DIR}/frontend/node_modules"

if [[ "${CTM_SKIP_MIGRATIONS:-0}" != "1" ]]; then
  echo "Running database migrations..."
  (
    cd "${ROOT_DIR}"
    alembic upgrade head
  )
fi

echo "Starting backend: http://${BACKEND_HOST}:${BACKEND_PORT}"
(
  cd "${ROOT_DIR}"
  uvicorn app.main:app --reload --host "${BACKEND_HOST}" --port "${BACKEND_PORT}"
) &
BACKEND_PID=$!

echo "Starting frontend: http://${FRONTEND_HOST}:${FRONTEND_PORT}"
(
  cd "${ROOT_DIR}/frontend"
  npm run dev -- --hostname "${FRONTEND_HOST}" --port "${FRONTEND_PORT}"
) &
FRONTEND_PID=$!

echo "Frontend and backend are starting."
echo "Frontend: http://${FRONTEND_HOST}:${FRONTEND_PORT}"
echo "Backend health: http://${BACKEND_HOST}:${BACKEND_PORT}/api/v1/health"

while true; do
  if ! kill -0 "${BACKEND_PID}" 2>/dev/null; then
    wait "${BACKEND_PID}"
    exit $?
  fi

  if ! kill -0 "${FRONTEND_PID}" 2>/dev/null; then
    wait "${FRONTEND_PID}"
    exit $?
  fi

  sleep 1
done
