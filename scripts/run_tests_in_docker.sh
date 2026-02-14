#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

WEB_SERVICE="${WEB_SERVICE:-web}"
DB_SERVICE="${DB_SERVICE:-db}"
TEST_DB_NAME="${TEST_DB_NAME:-insite_test}"
DEFAULT_DB_URL="postgresql://postgres:postgres@db:5432/${TEST_DB_NAME}"
TEST_DATABASE_URL="${TEST_DATABASE_URL:-${DATABASE_URL:-$DEFAULT_DB_URL}}"

echo "[Acceptance] Building ${WEB_SERVICE} with dev deps..."
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

echo "[Acceptance] Running reset + migrate + pytest inside ${WEB_SERVICE}..."
docker compose -p insite_signs run --rm \
  -e DATABASE_URL="${TEST_DATABASE_URL}" -e TEST_DB_NAME="${TEST_DB_NAME}" -e LOAD_DOTENV=0 \
  "${WEB_SERVICE}" bash -lc 'set -euo pipefail; echo "[Runner] Resetting test DB..."; python scripts/reset_test_db.py; echo "[Runner] Running migrations..."; python migrate.py; echo "[Runner] Running pytest..."; python scripts/check_pytest_fixtures.py; python -m pytest -q'

echo "[Acceptance] OK"
