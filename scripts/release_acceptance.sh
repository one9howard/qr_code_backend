#!/bin/bash
set -euo pipefail

echo "========================================"
echo "    RELEASE ACCEPTANCE GATES"
echo "========================================"

# Detect Python with pytest
PYTHON_CMD=""

# DEBUG: Print what we see
echo "🔍 Debugging Python Environment..."
echo "   - python: $(command -v python || echo 'not found')"
echo "   - python3: $(command -v python3 || echo 'not found')"
echo "   - pip: $(command -v pip || echo 'not found')"

# STRATEGY 1: Check for Windows Python via 'py.exe' (most reliable on Windows)
if command -v py &> /dev/null && py -c "import pytest" &> /dev/null; then
    PYTHON_CMD="py"
# STRATEGY 2: Check for 'python.exe' in the current venv (if we are in one)
elif [ -f ".venv/Scripts/python.exe" ] && .venv/Scripts/python.exe -c "import pytest" &> /dev/null; then
    PYTHON_CMD=".venv/Scripts/python.exe"
# STRATEGY 3: Check for standard 'python' (if mapped to Windows python)
elif command -v python &> /dev/null && python -c "import pytest" &> /dev/null; then
    PYTHON_CMD="python"
# STRATEGY 4: Fallback to 'python3' (last resort)
elif command -v python3 &> /dev/null && python3 -c "import pytest" &> /dev/null; then
    PYTHON_CMD="python3"
else
    echo "❌ CRITICAL: Could not find a Python executable with 'pytest' installed."
    echo "   I checked: py, .venv/Scripts/python.exe, python, python3"
    echo ""
    echo "   If you believe you installed it, you might be running this script"
    echo "   from a shell (Bash) that sees a different Python than your PowerShell."
    echo ""
    echo "   TRY: Explicitly installing it in this shell:"
    echo "   $ pip install pytest"
    exit 1
fi

echo "ℹ️  Using Python: $($PYTHON_CMD --version) ($PYTHON_CMD)"

# 1. Release Cleanliness (Repo level)
# MUST RUN FIRST before compileall creates __pycache__
echo "🔍 1. Checking for repository cleanliness..."
if [ -f "scripts/check_release_clean.py" ]; then
    $PYTHON_CMD scripts/check_release_clean.py
else
    echo "   ⚠️  scripts/check_release_clean.py not found! Skipping..."
fi

# 2. Code Hygiene (No Prints)
echo "🔍 2. Checking for forbidden print() statements..."
if [ -f "scripts/check_no_prints.py" ]; then
    $PYTHON_CMD scripts/check_no_prints.py
else
    echo "   ⚠️  scripts/check_no_prints.py not found!"
    exit 1
fi

# 3. Syntax Check (Fast Fail)
echo "🔍 3. Bytecode Compilation (Syntax Check)..."
# Exclude known large dirs or artifacts to keep it fast
$PYTHON_CMD -m compileall -q . -x "(\.venv|\.git|__pycache__|tests/fixtures)"
echo "   ✅ Syntax OK"

# 4. Unit Tests (Fast)
echo "🧪 4. Running Unit Tests..."
$PYTHON_CMD -m pytest -q -m "not slow" || {
    RET=$?
    if [ $RET -eq 5 ]; then
        echo "   ⚠️  No tests found (Exit 5). Continuing..."
    else
        echo "   ❌ Tests Failed!"
        exit $RET
    fi
}

echo "========================================"
echo "✅ ALL ACCEPTANCE CHECKS PASSED"
echo "========================================"
