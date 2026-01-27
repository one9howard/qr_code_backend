$ErrorActionPreference = "Stop"

# Force running from repo root
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RepoRoot
Write-Host "Running release checks in: $RepoRoot" -ForegroundColor Cyan

function Invoke-Check {
    param($Command, $Arguments)
    Write-Host "Running: $Command $Arguments" -ForegroundColor Yellow
    & $Command $Arguments
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAILURE: Command failed with exit code $LASTEXITCODE" -ForegroundColor Red
        exit 1
    }
}

# 1. Bytecode Compilation Check (Clean)
# First we clean up any potential existing bytecode to ensure we are testing source
Write-Host "Cleaning up bytecode..." -ForegroundColor Cyan
Get-ChildItem -Recurse -Force -file -Filter "*.pyc" -ErrorAction SilentlyContinue | Remove-Item -Force
Get-ChildItem -Recurse -Force -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force

# Run syntax check without writing .pyc files
Invoke-Check "python" @("-B", "scripts/syntax_check.py")

# 2. Release Cleanliness Check (Checks for debris that SHOULD NOT be there)
Invoke-Check "python" @("scripts/check_release_clean.py")

# 3. Security Sanity Check
Invoke-Check "python" @("scripts/security_sanity_check.py")

# 4. Import Safety Check
Invoke-Check "python" @("scripts/verify_import_safety.py")

# 5. Tests (Running in Docker container to avoid local environment pollution)
Write-Host "Building Docker test container..." -ForegroundColor Cyan
Invoke-Check "docker" @("compose", "build", "--no-cache", "--build-arg", "INSTALL_DEV=true", "web")

Write-Host "Running tests in Docker..." -ForegroundColor Cyan
Invoke-Check "docker" @("compose", "run", "--rm", "web", "python", "-m", "pytest", "-q")

# 6. Stripe Key Scan
Write-Host "Scanning for Stripe Keys..." -ForegroundColor Cyan
# Select-String doesn't have -Recurse, must use Get-ChildItem
# Exclude docker-compose.yml and .github directory (as CI check contains the pattern)
$StripeMatches = Get-ChildItem -Recurse -File | Where-Object { $_.FullName -notmatch "\\.github\\" -and $_.Name -ne "docker-compose.yml" } | Select-String -Pattern 'stripe\.api_key\s*='

$Failed = $false
foreach ($Match in $StripeMatches) {
    # Match object from pipeline has Path property
    $RelPath = $Match.Path.Substring($RepoRoot.Path.Length + 1).Replace("\", "/")
    
    # Strict Allowlist: ONLY services/stripe_client.py
    if ($RelPath -ne "services/stripe_client.py") {
        Write-Host "FORBIDDEN: stripe.api_key set in $RelPath" -ForegroundColor Red
        $Failed = $true
    }
}

if ($Failed) {
    Write-Host "FAILURE: Stripe API key set outside allowlist." -ForegroundColor Red
    exit 1
}

Write-Host "SUCCESS: No forbidden Stripe key assignments found." -ForegroundColor Green
Write-Host "All checks passed!" -ForegroundColor Green
exit 0
