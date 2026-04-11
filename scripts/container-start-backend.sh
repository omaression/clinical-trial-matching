#!/usr/bin/env bash

set -euo pipefail

PORT="${PORT:-8000}"
WEB_CONCURRENCY="${WEB_CONCURRENCY:-1}"
UVICORN_LOG_LEVEL="${UVICORN_LOG_LEVEL:-info}"

if [[ "${CTM_RUN_MIGRATIONS:-0}" == "1" ]]; then
  echo "Running Alembic migrations before API startup..."
  alembic upgrade head
fi

exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT}" \
  --workers "${WEB_CONCURRENCY}" \
  --log-level "${UVICORN_LOG_LEVEL}"
