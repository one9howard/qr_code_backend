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
TEST_DATABASE_URL="${TEST_DATABASE_URL:-${DATABASE_URL:-}}"

if [[ -z "${TEST_DATABASE_URL}" ]]; then
  echo "[Acceptance] ERROR: TEST_DATABASE_URL (or DATABASE_URL) is required."
  echo "  Example: export TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/${TEST_DB_NAME}"
  exit 1
fi

echo "[Acceptance] Building ${WEB_SERVICE} with dev deps..."
docker compose build --no-cache --build-arg INSTALL_DEV=true "${WEB_SERVICE}"

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
  "${WEB_SERVICE}" \
  bash -lc "set -euo pipefail \
    && python scripts/reset_test_db.py \
    && python migrate.py \
    && python -m pytest -q"

echo "[Acceptance] OK"
