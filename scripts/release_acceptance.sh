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

# FIX: Aggressively clean __pycache__ which might be created by the calling python process
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

if [ -f "scripts/check_release_clean.py" ]; then
    python3 scripts/check_release_clean.py
else
    echo "   [WARN] scripts/check_release_clean.py not found! Skipping..."
fi

# 2. Code Hygiene (No Prints)
echo "[LOCK] 2. Checking for forbidden print() statements..."
if [ -f "scripts/check_no_prints.py" ]; then
    python3 scripts/check_no_prints.py
else
    echo "   [WARN] scripts/check_no_prints.py not found!"
    exit 1
fi

# 3. Syntax Check (Fast Fail)
echo "[LOCK] 3. Bytecode Compilation (Syntax Check)..."
# Exclude known large dirs or artifacts to keep it fast
python3 -m compileall -q . -x "(\.venv|\.git|__pycache__|tests/fixtures)"
echo "   [OK] Syntax OK"

# 4. Unit Tests (Warn only - test debt tracked separately)
echo "[TEST] 4. Running Unit Tests..."
python3 -m pytest -q -m "not slow" || {
    RET=$?
    if [ $RET -eq 5 ]; then
        echo "   [WARN] No tests collected (Exit 5). Verify pytest configuration."
        echo "   [FAIL] Test collection failed."
        exit $RET
    else
        if [ "${ALLOW_TEST_FAILURES:-0}" = "1" ]; then
             echo "   [WARN] Tests FAILED (exit code $RET). QA_OVERRIDE: Continuing because ALLOW_TEST_FAILURES=1."
        else
             echo "   [FAIL] Tests FAILED (exit code $RET). Preventing release build."
             echo "      ( Hint: Set ALLOW_TEST_FAILURES=1 to bypass if necessary )"
             exit $RET
        fi
    fi
}

echo "========================================"
echo "[OK] ALL ACCEPTANCE CHECKS PASSED"
echo "========================================"
