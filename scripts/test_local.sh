#!/bin/bash
# scripts/test_local.sh
# Boot db, migrate, run pytest. Exit non-zero on any failure.

set -e  # Exit on first error

echo "=== Phase 0 Local Test Runner ==="
echo ""

# 1. Boot database
echo "[1/4] Starting database container..."
docker compose up -d db
echo "Waiting for database to be ready..."
sleep 5

# 2. Set DATABASE_URL for local connection
export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/insite_test"
echo "[2/4] DATABASE_URL set to: $DATABASE_URL"

# 3. Run migrations
echo "[3/4] Running migrations..."
python migrate.py
if [ $? -ne 0 ]; then
    echo "FAIL: migrate.py failed"
    exit 1
fi
echo "Migrations complete."

# 4. Run tests
echo "[4/4] Running pytest..."
python -m pytest -q
if [ $? -ne 0 ]; then
    echo "FAIL: pytest failed"
    exit 1
fi

echo ""
echo "=== All tests passed! Phase 0 is stable. ==="
exit 0
