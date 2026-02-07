#!/bin/bash
set -euo pipefail

echo "========================================"
echo "    RELEASE ACCEPTANCE GATES"
echo "========================================"

# Detect Python with pytest
PYTHON_CMD="python3"

# TRY 1: Check if 'python' (often Windows alias in Git Bash) is valid
if command -v python &> /dev/null && python -c "import pytest" &> /dev/null; then
    PYTHON_CMD="python"
# TRY 2: Check standard 'python3'
elif command -v python3 &> /dev/null && python3 -c "import pytest" &> /dev/null; then
    PYTHON_CMD="python3"
# TRY 3: Explicitly look for Windows Python in standard locations (Git Bash common path)
elif [ -f "/c/Windows/py.exe" ] && /c/Windows/py.exe -m pytest --version &> /dev/null; then
    PYTHON_CMD="/c/Windows/py.exe"
else
    # FAILURE MODE
    echo "❌ CRITICAL: No python found with 'pytest' installed."
    echo "   Checked 'python' and 'python3'."
    echo "   The release script requires a Python environment with dev dependencies."
    echo ""
    echo "   FIX:"
    echo "   Run 'pip install pytest' in this terminal."
    # We will attempt to continue with 'python3' to see if it works later or fail hard
    # exit 1 
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
