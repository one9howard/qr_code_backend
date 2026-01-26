#!/usr/bin/env bash
set -euo pipefail

ROLE="${SERVICE_ROLE:-web}"

if [[ "$ROLE" == "worker" ]]; then
  echo "[railway] starting print worker"
  exec python scripts/print_worker.py
else
  echo "[railway] starting web"
  exec gunicorn --workers 3 --bind 0.0.0.0:${PORT} --log-level debug --access-logfile - --error-logfile - app:app
fi
