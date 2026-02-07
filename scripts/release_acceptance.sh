#!/bin/bash
set -euo pipefail

# Parse arguments
ALLOW_TEST_FAILURES=${ALLOW_TEST_FAILURES:-0}
for arg in "$@"; do
  case $arg in
    --allow-test-failures)
      ALLOW_TEST_FAILURES=1
      shift
      ;;
  esac
done

export PYTHONDONTWRITEBYTECODE=1

echo "========================================"
echo "    RELEASE ACCEPTANCE GATES"
echo "========================================"

# 1. Release Cleanliness (Repo level)
# MUST RUN FIRST before compileall creates __pycache__
echo "[LOCK] 1. Checking for repository cleanliness..."

# NOTE: Do not mutate the workspace here. If __pycache__ exists, this gate must fail.

PYTHON=${PYTHON_EXEC:-python}

if [ -f "scripts/check_release_clean.py" ]; then
    $PYTHON scripts/check_release_clean.py
else
    echo "   [WARN] scripts/check_release_clean.py not found! Skipping..."
fi

# 2. Code Hygiene (No Prints)
echo "[LOCK] 2. Checking for forbidden print() statements..."
if [ -f "scripts/check_no_prints.py" ]; then
    $PYTHON scripts/check_no_prints.py
else
    echo "   [FAIL] scripts/check_no_prints.py not found!"
    exit 1
fi

# 3. Syntax Check (Fast Fail)
echo "[LOCK] 3. Bytecode Compilation (Syntax Check)..."
# Exclude known large dirs or artifacts to keep it fast
$PYTHON -m compileall -q . -x "(\.venv|\.git|__pycache__|tests/fixtures)"
echo "   [OK] Syntax OK"

# 4. Unit Tests (Strict)
echo "[TEST] 4. Running Unit Tests..."
$PYTHON -m pytest -q -m "not slow" || {
    RET=$?
    echo "   [FAIL] Tests FAILED (exit code $RET). Preventing release build."
    exit $RET
}
echo "   [OK] Tests Passed"

# 5. Migration Runner Check
echo "[TEST] 5. Checking for canonical migration runner..."
if [ -f "migrate.py" ] && [ -f "alembic.ini" ]; then
    echo "   [OK] migrate.py and alembic.ini found."
else
    echo "   [FAIL] Canonical migration runner (migrate.py) or config (alembic.ini) missing!"
    exit 1
fi

echo "========================================"
echo "[OK] ALL ACCEPTANCE CHECKS PASSED"
echo "========================================"
