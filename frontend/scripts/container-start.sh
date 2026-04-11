#!/usr/bin/env sh

set -eu

PORT="${PORT:-3000}"

exec npm run start -- --hostname 0.0.0.0 --port "${PORT}"
