# Reset QR Code Business App Data
# Removes database, generated files, and runtime data for fresh start

Write-Host "=== QR Code App Reset ===" -ForegroundColor Cyan
Write-Host ""

# Configuration
$DB_FILE = "instance/qr.db"
$GENERATED_DIRS = @(
    "static/qr",
    "static/signs", 
    "static/pdf",
    "static/uploads",
    "static/generated",
    "private",
    "print_inbox",
    "releases",
    "logs"
)

# 1. Delete Database
Write-Host "Checking database..." -ForegroundColor Yellow
if (Test-Path $DB_FILE) {
    Remove-Item $DB_FILE -Force
    Remove-Item "$DB_FILE-journal" -Force -ErrorAction SilentlyContinue
    Remove-Item "$DB_FILE-wal" -Force -ErrorAction SilentlyContinue
    Remove-Item "$DB_FILE-shm" -Force -ErrorAction SilentlyContinue
    Write-Host "  Database ($DB_FILE) deleted." -ForegroundColor Green
}
else {
    Write-Host "  Database ($DB_FILE) not found." -ForegroundColor Gray
}

# 2. Clear Generated Assets
Write-Host ""
$response = Read-Host "Delete all generated files (QRs, PDFs, uploads, releases)? (y/n)"
if ($response -eq 'y') {
    foreach ($path in $GENERATED_DIRS) {
        if (Test-Path $path) {
            Get-ChildItem -Path $path -Recurse -File | Remove-Item -Force -ErrorAction SilentlyContinue
            Write-Host "  Cleared: $path" -ForegroundColor Green
        }
    }
}

# 3. Optionally remove virtual environment
Write-Host ""
$response = Read-Host "Delete virtual environment (.venv)? This requires reinstall. (y/n)"
if ($response -eq 'y') {
    if (Test-Path ".venv") {
        Remove-Item -Recurse -Force ".venv"
        Write-Host "  Virtual environment deleted." -ForegroundColor Green
        Write-Host "  Run: python -m venv .venv && .\.venv\Scripts\Activate.ps1" -ForegroundColor Yellow
        Write-Host "       pip install pip-tools && pip-sync requirements.txt requirements-dev.txt" -ForegroundColor Yellow
    }
    else {
        Write-Host "  .venv not found." -ForegroundColor Gray
    }
}

Write-Host ""
Write-Host "=== Reset Complete ===" -ForegroundColor Cyan
Write-Host "Restart the application to recreate the database." -ForegroundColor White
