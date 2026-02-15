#!/usr/bin/env bash
set -euo pipefail

ROLE="${SERVICE_ROLE:-web}"

if [[ "$ROLE" == "worker" ]]; then
  echo "[railway] starting async worker"
  exec python scripts/async_worker.py
else
  echo "[railway] starting web via docker-entrypoint"
  export RUN_MIGRATIONS_ON_STARTUP="${RUN_MIGRATIONS_ON_STARTUP:-true}"
  exec /app/scripts/docker-entrypoint.sh sh -c "echo '[Gunicorn] Starting on port: ${PORT:-8080}' && exec gunicorn --workers ${WEB_CONCURRENCY:-3} --bind 0.0.0.0:${PORT:-8080} --log-level info --access-logfile - --error-logfile - app:app"
fi
