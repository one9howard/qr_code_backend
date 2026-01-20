#!/usr/bin/env bash
# QR Code Backend - Linux/macOS Bootstrap Script
# Creates venv, installs pip-tools, syncs dependencies, runs tests

set -e

echo "=== QR Code Backend Bootstrap (Linux/macOS) ==="

# Check Python version
python3 --version

# Create venv if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

# Activate venv
echo "Activating virtual environment..."
source .venv/bin/activate

# Upgrade pip/setuptools/wheel
echo "Upgrading pip, setuptools, wheel..."
python -m pip install -U pip setuptools wheel --quiet

# Install pip-tools
echo "Installing pip-tools..."
python -m pip install pip-tools --quiet

# Sync dependencies
echo "Syncing dependencies with pip-sync..."
pip-sync requirements.txt requirements-dev.txt

echo ""
echo "=== Installation Complete ==="

# Run tests unless --skip-tests flag passed
if [ "$1" != "--skip-tests" ]; then
    echo ""
    echo "=== Running Tests ==="
    pytest -q
fi
