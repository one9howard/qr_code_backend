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

PYTHON=${PYTHON_EXEC:-python}

# 1. Bytecode Isolation
# Use a temp directory for pycache that Windows Python understands
PYCACHE_TMP=$("$PYTHON" -c "import tempfile; print(tempfile.mkdtemp())")
export PYTHONPYCACHEPREFIX="$PYCACHE_TMP"
export PYTHONDONTWRITEBYTECODE=1
# Cleanup on exit
trap 'rm -rf "$PYCACHE_TMP"' EXIT

echo "========================================"
echo "    RELEASE ACCEPTANCE GATES"
echo "========================================"

# 2. Release Cleanliness (Repo level)
# MUST RUN FIRST before any gates can potentially dirty the repo
echo "[LOCK] 1. Checking for repository cleanliness..."

if [ -f "scripts/check_release_clean.py" ]; then
    "$PYTHON" scripts/check_release_clean.py
else
    echo "   [WARN] scripts/check_release_clean.py not found! Skipping..."
fi

# 3. Code Hygiene (No Prints)
echo "[LOCK] 2. Checking for forbidden print() statements..."
if [ -f "scripts/check_no_prints.py" ]; then
    "$PYTHON" scripts/check_no_prints.py
else
    echo "   [FAIL] scripts/check_no_prints.py not found!"
    exit 1
fi

# 4. Syntax Check (Fast Fail)
echo "[LOCK] 3. Syntax Verification (No Disk Write)..."
# We check every python file in the repo for syntax errors.
# We redirect output to os.devnull to ensure no __pycache__ or .pyc files are created.
"$PYTHON" -c "
import py_compile, os, sys
root = '.' 
errors = 0
for r, d, f in os.walk(root):
    if any(s in r for s in ['.git', '.venv', 'venv', 'node_modules', '__pycache__']): continue
    for file in f:
        if file.endswith('.py'):
            try:
                # Compile to devnull to check syntax without artifacts
                py_compile.compile(os.path.join(r, file), cfile=os.devnull, doraise=True)
            except Exception as e:
                print(f'   [FAIL] Syntax error in {os.path.join(r, file)}: {e}')
                errors += 1
if errors: sys.exit(1)
"
echo "   [OK] Syntax Verification Passed"

# 5. Unit Tests (Strict)
echo "[TEST] 4. Running Unit Tests..."
PYTHONPYCACHEPREFIX="$PYCACHE_TMP" "$PYTHON" -m pytest -q -m "not slow" || {
    RET=$?
    echo "   [FAIL] Tests FAILED (exit code $RET). Preventing release build."
    exit $RET
}
echo "   [OK] Tests Passed"

# 6. Migration Runner Check
echo "[TEST] 5. Checking for canonical migration runner..."
if [ -f "migrate.py" ] && [ -f "alembic.ini" ]; then
    echo "   [OK] migrate.py and alembic.ini found."
else
    echo "   [FAIL] Canonical migration runner (migrate.py) or config (alembic.ini) missing!"
    exit 1
fi

# Final Verification: Ensure we didn't leave any trash
if [ -f "scripts/check_release_clean.py" ]; then
    "$PYTHON" scripts/check_release_clean.py
fi

echo "========================================"
echo "[OK] ALL ACCEPTANCE CHECKS PASSED"
echo "========================================"
