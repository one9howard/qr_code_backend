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
docker compose build "${BUILD_FLAGS[@]}" --build-arg INSTALL_DEV=true "${WEB_SERVICE}"

echo "[Acceptance] Starting ${DB_SERVICE}..."
# --wait exists on newer compose; don't hard-require it.
if docker compose up -d --wait "${DB_SERVICE}" 2>/dev/null; then
  :
else
  docker compose up -d "${DB_SERVICE}"
fi

echo "[Acceptance] Running reset + migrate + pytest inside ${WEB_SERVICE}..."
# Run as a single in-container shell so failures stop the whole chain.
docker compose run --rm \
  -e DATABASE_URL="${TEST_DATABASE_URL}" \
  -e TEST_DB_NAME="${TEST_DB_NAME}" \
  -e DISABLE_DOTENV=1 \
  "${WEB_SERVICE}" \
  bash -lc "set -euo pipefail \
    && python scripts/reset_test_db.py \
    && python migrate.py \
    && python -m pytest -q"

echo "[Acceptance] OK"
