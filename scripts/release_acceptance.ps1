$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $root

$webService = $env:WEB_SERVICE
if ([string]::IsNullOrWhiteSpace($webService)) { $webService = "web" }

$dbService = $env:DB_SERVICE
if ([string]::IsNullOrWhiteSpace($dbService)) { $dbService = "db" }

$testDbName = $env:TEST_DB_NAME
if ([string]::IsNullOrWhiteSpace($testDbName)) { $testDbName = "insite_test" }

$testDatabaseUrl = $env:TEST_DATABASE_URL
if ([string]::IsNullOrWhiteSpace($testDatabaseUrl)) { $testDatabaseUrl = $env:DATABASE_URL }

# On Windows, run Docker commands directly (no bash delegation)
# The .sh canonical runner is for CI/Linux environments

if ([string]::IsNullOrWhiteSpace($testDatabaseUrl)) {
    # Default for local testing
    $testDatabaseUrl = "postgresql://postgres:postgres@localhost:5432/$testDbName"
}

Write-Host "[Acceptance] Building $webService with dev deps..."
docker compose build --no-cache --build-arg INSTALL_DEV=true $webService
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "[Acceptance] Starting $dbService..."
docker compose up -d $dbService
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "[Acceptance] Waiting for database to be healthy..."
$retries = 30
while ($retries -gt 0) {
    $result = docker compose exec -T $dbService pg_isready -U postgres 2>$null
    if ($LASTEXITCODE -eq 0) { break }
    Start-Sleep -Seconds 1
    $retries--
}
if ($retries -eq 0) {
    Write-Host "[Acceptance] ERROR: Database did not become healthy in time." -ForegroundColor Red
    docker compose down
    exit 1
}
Write-Host "[Acceptance] Database is healthy."

Write-Host "[Acceptance] Running reset + migrate + pytest inside $webService..."
docker compose run --rm `
    -e DATABASE_URL="$testDatabaseUrl" `
    -e TEST_DB_NAME="$testDbName" `
    $webService `
    bash -lc "set -euo pipefail && python scripts/reset_test_db.py && python migrate.py && python -m pytest -q"

$testResult = $LASTEXITCODE

Write-Host "[Acceptance] Cleaning up..."
docker compose down

if ($testResult -ne 0) {
    Write-Host "[Acceptance] FAILED with exit code $testResult" -ForegroundColor Red
    exit $testResult
}

Write-Host "[Acceptance] OK" -ForegroundColor Green
