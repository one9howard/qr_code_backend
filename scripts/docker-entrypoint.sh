#!/bin/bash
set -e

# 1. Database Migrations (Gated)
# Only run if explicitly enabled via environment variable
if [ "$RUN_MIGRATIONS_ON_STARTUP" = "true" ]; then
  echo "[Entrypoint] RUN_MIGRATIONS_ON_STARTUP is true. Attempting migrations..."

  if [ -n "$DATABASE_URL" ]; then
    echo "[Entrypoint] Detected DATABASE_URL. Waiting for DB..."
    python3 /app/scripts/wait_for_db.py
    echo "[Entrypoint] DB ready. Running Alembic..."
  else
    echo "[Entrypoint] ERROR: DATABASE_URL is not set. Postgres is required."
    exit 1
  fi

  python3 migrate.py
  python3 migrate.py
else
  echo "[Entrypoint] Skipping migrations (RUN_MIGRATIONS_ON_STARTUP is not true)."
fi

# 2. Start Application
echo "[Entrypoint] Starting application..."
echo "[Entrypoint] Executing: $@"
exec "$@"
