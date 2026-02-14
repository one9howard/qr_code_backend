#!/bin/bash
set -euo pipefail

if [ "${RUN_MIGRATIONS_ON_STARTUP:-}" = "true" ]; then

  if [ -n "${DATABASE_URL:-}" ]; then
    echo "[Entrypoint] Detected DATABASE_URL. Waiting for DB..."
    python3 /app/scripts/wait_for_db.py
    echo "[Entrypoint] DB ready. Running Alembic..."
  else
    echo "[Entrypoint] ERROR: DATABASE_URL is not set. Postgres is required."
    exit 1
  fi

  python3 /app/migrate.py
else
  echo "[Entrypoint] Skipping migrations (RUN_MIGRATIONS_ON_STARTUP is not true)."
fi

if [ -n "${DATABASE_URL:-}" ]; then
  echo "[Entrypoint] Validating schema..."
  python3 /app/scripts/check_schema_ready.py
fi

echo "[Entrypoint] Starting application..."
echo "[Entrypoint] Executing: $@"
exec "$@"
