# QR Code Backend - Windows Bootstrap Script
# Creates venv, installs pip-tools, syncs dependencies, runs tests

param(
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"

Write-Host "=== QR Code Backend Bootstrap (Windows) ===" -ForegroundColor Cyan

# Check Python version
$pythonVersion = python --version 2>&1
Write-Host "Using: $pythonVersion"

# Create venv if it doesn't exist
if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment..." -ForegroundColor Yellow
    python -m venv .venv
}

# Activate venv
Write-Host "Activating virtual environment..." -ForegroundColor Yellow
& .\.venv\Scripts\Activate.ps1

# Upgrade pip/setuptools/wheel
Write-Host "Upgrading pip, setuptools, wheel..." -ForegroundColor Yellow
python -m pip install -U pip setuptools wheel --quiet

# Install pip-tools
Write-Host "Installing pip-tools..." -ForegroundColor Yellow
python -m pip install pip-tools --quiet

# Sync dependencies
Write-Host "Syncing dependencies with pip-sync..." -ForegroundColor Yellow
pip-sync requirements.txt requirements-dev.txt

Write-Host ""
Write-Host "=== Installation Complete ===" -ForegroundColor Green

# Run tests unless skipped
if (-not $SkipTests) {
    Write-Host ""
    Write-Host "=== Running Tests ===" -ForegroundColor Cyan
    pytest -q
}
