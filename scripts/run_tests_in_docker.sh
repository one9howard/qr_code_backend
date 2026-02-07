#!/bin/bash
# Canonical Docker-based test runner for release acceptance.
# This is the ONE source of truth for running tests in a reproducible environment.

set -euo pipefail

echo "========================================"
echo "  CANONICAL DOCKER TEST RUNNER"
echo "========================================"

# 1. Build web container with test dependencies
echo "[1/4] Building web container with INSTALL_DEV=true..."
docker compose build --no-cache --build-arg INSTALL_DEV=true web

# 2. Start the database
echo "[2/4] Starting database container..."
docker compose up -d db

# Wait for db to be healthy
echo "      Waiting for database to be healthy..."
RETRIES=30
until docker compose exec -T db pg_isready -U postgres > /dev/null 2>&1 || [ $RETRIES -eq 0 ]; do
  echo "      Waiting for postgres... ($RETRIES retries left)"
  RETRIES=$((RETRIES-1))
  sleep 1
done

if [ $RETRIES -eq 0 ]; then
  echo "[FAIL] Database did not become healthy in time."
  docker compose down
  exit 1
fi
echo "      Database is healthy."

# 3. Reset and migrate test database
echo "[3/4] Resetting and migrating test database..."
docker compose run --rm web python scripts/reset_test_db.py
docker compose run --rm web python migrate.py

# 4. Run tests
echo "[4/4] Running pytest..."
docker compose run --rm web python -m pytest -q

TEST_EXIT_CODE=$?

# Cleanup
echo "Cleaning up containers..."
docker compose down

if [ $TEST_EXIT_CODE -ne 0 ]; then
  echo "========================================"
  echo "[FAIL] Tests failed with exit code $TEST_EXIT_CODE"
  echo "========================================"
  exit $TEST_EXIT_CODE
fi

echo "========================================"
echo "[OK] All tests passed!"
echo "========================================"
exit 0
