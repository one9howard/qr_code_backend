# Test Runner for Windows (PowerShell)
# Installs test dependencies and runs pytest with correct environment.

Write-Host "Setting up test environment..."

# 1. Install Dependencies
Write-Host "Installing application dependencies..."
pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to install requirements.txt"
    exit 1
}

Write-Host "Installing test dependencies..."
pip install -r requirements-test.txt
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to install requirements-test.txt"
    exit 1
}

# 2. Set Environment Variables
$env:FLASK_ENV = "testing"
$env:IS_PRODUCTION = "false"
$env:DATABASE_URL = "postgresql://user:password@localhost/test_db" # Mock or override in conftest
$env:STRIPE_SECRET_KEY = "sk_test_mock"
$env:SECRET_KEY = "dev_secret_key"
$env:STORAGE_BACKEND = "local"

# 3. Clean Artifacts first (optional but good for consistency)
python scripts/clean_artifacts.py

# 4. Run Tests
Write-Host "Running tests..."
# -v for verbose, -s to show stdout/stderr
python -m pytest -v -s

if ($LASTEXITCODE -ne 0) {
    Write-Error "Tests FAILED."
    exit 1
}

Write-Host "Tests PASSED."
exit 0
