#!/usr/bin/env bash
set -euo pipefail

# Canonical, un-bypassable acceptance runner.
# This is the ONLY place that defines the release test sequence.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

WEB_SERVICE="${WEB_SERVICE:-web}"
DB_SERVICE="${DB_SERVICE:-db}"

# Prefer explicit TEST_DATABASE_URL; otherwise fall back to DATABASE_URL.
# Keep this deterministic: we want the same DB name everywhere.
TEST_DB_NAME="${TEST_DB_NAME:-insite_test}"
# Default to internal docker service DNS if not set
DEFAULT_DB_URL="postgresql://postgres:postgres@db:5432/${TEST_DB_NAME}"
TEST_DATABASE_URL="${TEST_DATABASE_URL:-${DATABASE_URL:-$DEFAULT_DB_URL}}"

echo "[Acceptance] Building ${WEB_SERVICE} with dev deps..."
# R1: Build Caching Optimization
NO_CACHE="${NO_CACHE:-0}"
BUILD_FLAGS=()
if [[ "$NO_CACHE" == "1" ]]; then 
  BUILD_FLAGS+=(--no-cache)
fi
docker compose -p insite_signs build "${BUILD_FLAGS[@]}" --build-arg INSTALL_DEV=true "${WEB_SERVICE}"

echo "[Acceptance] Starting ${DB_SERVICE}..."
# --wait exists on newer compose; don't hard-require it.
if docker compose -p insite_signs up -d --wait "${DB_SERVICE}" 2>/dev/null; then
  :
else
  docker compose -p insite_signs up -d "${DB_SERVICE}"
fi

# Ensure .env exists so docker compose doesn't fail mounting it
# No env_file requirement in docker-compose; keep runner hermetic and non-destructive.
CREATED_ENV="0"
if [ ! -f .env ]; then touch .env; CREATED_ENV="1"; fi
  if [ "${CREATED_ENV}" = "1" ]; then rm -f .env; fi

echo "[Acceptance] Running reset + migrate + pytest inside ${WEB_SERVICE}..."
# Run as a single in-container shell so failures stop the whole chain.
docker compose -p insite_signs run --rm \
  -e DATABASE_URL="${TEST_DATABASE_URL}" \
  -e TEST_DB_NAME="${TEST_DB_NAME}" \
  "${WEB_SERVICE}" \
  bash -lc "set -euo pipefail \
    && python scripts/reset_test_db.py \
    # Hermeticity check: ensure migrate.py does NOT load .env unless LOAD_DOTENV=1 \
    && ENV_BAK=0 \
    && if [ -f .env ]; then cp .env .env.__bak && ENV_BAK=1; fi \
    && echo 'DATABASE_URL=postgresql://should_not_use' > .env \
    && MIGRATE_LOG=\$(python migrate.py 2>&1) \
    && echo \"\$MIGRATE_LOG\" \
    && (echo \"\$MIGRATE_LOG\" | grep -q \"Loaded .env file\" && echo \"[Acceptance] ERROR: migrate.py loaded .env unexpectedly\" && exit 1 || true) \
    && if [ "\$ENV_BAK" = "1" ]; then mv .env.__bak .env; else rm -f .env; fi \
    && python -m pytest -q"

echo "[Acceptance] OK"
