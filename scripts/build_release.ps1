# Wrapper script for clean release builds on Windows
# Prevents self-generated __pycache__ from failing the cleanliness check.

Write-Host "🧹 Cleaning existing __pycache__ directories..."
Get-ChildItem -Path . -Include __pycache__ -Recurse -Directory -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force

Write-Host "🚀 Starting Release Build (PYTHONDONTWRITEBYTECODE=1)..."
$env:PYTHONDONTWRITEBYTECODE = 1
python scripts/build_release_zip.py

if ($LASTEXITCODE -eq 0) {
    Write-Host "✨ Release Build Complete!" -ForegroundColor Green
}
else {
    Write-Host "❌ Release Build Failed." -ForegroundColor Red
    exit $LASTEXITCODE
}
