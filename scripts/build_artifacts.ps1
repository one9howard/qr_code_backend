# scripts/build_artifacts.ps1
# Produces two zips:
#  1) Repo ZIP (for code review) - includes tests/CI, excludes secrets and runtime artifacts
#  2) Release ZIP (for shipping) - delegates to scripts/build_release_zip.py
# Also runs security_sanity_check + pytest first.

$ErrorActionPreference = "Stop"

# Get repo root (parent of scripts/)
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repoRoot

# Prefer venv python if present, else fallback
$venvPy = Join-Path $repoRoot ".venv\Scripts\python.exe"
$py = if (Test-Path $venvPy) { $venvPy } else { "python" }

# Output dirs
$releaseDir = Join-Path $repoRoot "releases"
New-Item -ItemType Directory -Force -Path $releaseDir | Out-Null

# Timestamp
$ts = Get-Date -Format "yyyyMMdd_HHmmss"

Write-Host "== Repo root: $repoRoot"
Write-Host "== Using python: $py"
Write-Host "== Timestamp: $ts"
Write-Host ""

# ---------------------------------------------------------------------
# 1) Guardrails: forbidden files should not be present
# ---------------------------------------------------------------------
Write-Host "== Running security sanity check..."
& $py "scripts\security_sanity_check.py"
Write-Host "OK"
Write-Host ""

# ---------------------------------------------------------------------
# 2) Tests
# ---------------------------------------------------------------------
Write-Host "== Running tests..."
& $py "-m" "pytest" "-q"
Write-Host "OK"
Write-Host ""

# ---------------------------------------------------------------------
# 3) Build REPO zip (for code review)
#    Includes tests/ and CI configs; excludes secrets/artifacts/caches.
# ---------------------------------------------------------------------
Write-Host "== Building repo/worktree zip (for review)..."

$stagingRoot = Join-Path $releaseDir "_staging_repo_$ts"
$stagingApp = Join-Path $stagingRoot "qr_code_backend_repo"

# Clean staging
if (Test-Path $stagingRoot) { Remove-Item -Recurse -Force $stagingRoot }
New-Item -ItemType Directory -Force -Path $stagingApp | Out-Null

# Copy everything, excluding heavy/unsafe dirs using robocopy
# (robocopy exit codes: 0-7 are success; >=8 is failure)
$excludeDirs = @(
    ".git", ".venv", "venv", "__pycache__", ".pytest_cache",
    "private", "print_inbox", "releases", "node_modules"
)

# Robocopy requires absolute paths for reliability
$src = $repoRoot
$dst = $stagingApp

$robocopyArgs = @(
    $src, $dst,
    "/E", "/NFL", "/NDL", "/NJH", "/NJS", "/NP",
    "/XD"
) + $excludeDirs

$rc = & robocopy @robocopyArgs
if ($LASTEXITCODE -ge 8) {
    throw "robocopy failed with exit code $LASTEXITCODE"
}

# Remove forbidden files post-copy (keep .env.example)
$forbiddenPatterns = @(
    ".env", ".env.*", "*.db",
    "*.zip"  # prevent nested zips in repo artifact
)

Get-ChildItem -Path $stagingApp -Recurse -Force -File | ForEach-Object {
    $name = $_.Name
    $full = $_.FullName

    # Keep .env.example
    if ($name -ieq ".env.example") { return }

    # Match forbidden patterns
    foreach ($pat in $forbiddenPatterns) {
        if ($name -like $pat) {
            Remove-Item -Force $full
            break
        }
    }
}

# Also remove any leftover empty forbidden dirs if they slipped in
$forbiddenDirs = @("private", "print_inbox", ".git", "releases", ".venv", "venv")
Get-ChildItem -Path $stagingApp -Recurse -Force -Directory | Where-Object {
    $forbiddenDirs -contains $_.Name
} | ForEach-Object {
    Remove-Item -Recurse -Force $_.FullName
}

$repoZip = Join-Path $releaseDir ("qr_code_backend_repo_" + $ts + ".zip")
if (Test-Path $repoZip) { Remove-Item -Force $repoZip }

Compress-Archive -Path $stagingApp -DestinationPath $repoZip -Force

# Cleanup staging
Remove-Item -Recurse -Force $stagingRoot

Write-Host "OK -> $repoZip"
Write-Host ""

# ---------------------------------------------------------------------
# 4) Build RELEASE zip (for shipping) using your existing builder
# ---------------------------------------------------------------------
Write-Host "== Building release zip (for shipping)..."
& $py "scripts\build_release_zip.py"
Write-Host "OK"
Write-Host ""

Write-Host "DONE."
Write-Host "Repo/worktree zip (for review): $repoZip"
Write-Host "Release zip (for shipping): check the releases/ folder for the newest *_release*.zip"
