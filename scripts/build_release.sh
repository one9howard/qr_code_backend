#!/bin/bash
# build_release.sh - Create clean deployment package excluding secrets and user data

set -e

# Configuration
RELEASE_DIR="release"
ARCHIVE_NAME="qr_code_backend_release.tar.gz"

echo "Building clean release package..."

# 1. Remove old release if exists
if [ -d "$RELEASE_DIR" ]; then
    echo "Removing old release directory..."
    rm -rf "$RELEASE_DIR"
fi

# 2. Create release directory structure
mkdir -p "$RELEASE_DIR"

# 3. Copy application files (exclude sensitive/generated)
echo "Copying application files..."

# Copy Python code
cp -r routes "$RELEASE_DIR/"
cp -r services "$RELEASE_DIR/"
cp -r utils "$RELEASE_DIR/"
cp -r templates "$RELEASE_DIR/"
cp -r static "$RELEASE_DIR/" || true

# Copy scripts (excluding this build script is optional)
mkdir -p "$RELEASE_DIR/scripts"
cp scripts/*.py "$RELEASE_DIR/scripts/" 2>/dev/null || true
cp scripts/*.ps1 "$RELEASE_DIR/scripts/" 2>/dev/null || true
cp scripts/*.sh "$RELEASE_DIR/scripts/" 2>/dev/null || true

# Copy configuration templates (not actual .env!)
cp .env.example "$RELEASE_DIR/"

# Copy Python app files
cp app.py "$RELEASE_DIR/"
cp config.py "$RELEASE_DIR/"
cp constants.py "$RELEASE_DIR/"
cp database.py "$RELEASE_DIR/"
cp models.py "$RELEASE_DIR/"

# Copy pip-tools files (input and lockfiles)
cp requirements.in "$RELEASE_DIR/"
cp requirements.txt "$RELEASE_DIR/"
cp requirements-dev.in "$RELEASE_DIR/"
cp requirements-dev.txt "$RELEASE_DIR/"

# Copy reset scripts
cp reset_app.ps1 "$RELEASE_DIR/" 2>/dev/null || true
cp reset_app.sh "$RELEASE_DIR/" 2>/dev/null || true

# Copy documentation
cp README.md "$RELEASE_DIR/"

# Deployment docs live under docs/
cp docs/DEPLOYMENT.md "$RELEASE_DIR/DEPLOYMENT.md"
cp docs/DEPLOYMENT_OPS.md "$RELEASE_DIR/DEPLOYMENT_OPS.md" 2>/dev/null || true
cp docs/RAILWAY_DEPLOYMENT.md "$RELEASE_DIR/RAILWAY_DEPLOYMENT.md" 2>/dev/null || true

# 4. Create empty data directories
echo "Creating empty data directories..."
mkdir -p "$RELEASE_DIR/static/qr"
mkdir -p "$RELEASE_DIR/static/signs"
mkdir -p "$RELEASE_DIR/static/pdf"
mkdir -p "$RELEASE_DIR/static/uploads/properties"
mkdir -p "$RELEASE_DIR/print_inbox"
mkdir -p "$RELEASE_DIR/private/pdf"
mkdir -p "$RELEASE_DIR/private/previews"

# Add placeholder files to preserve empty dirs
touch "$RELEASE_DIR/static/qr/.keep"
touch "$RELEASE_DIR/static/signs/.keep"
touch "$RELEASE_DIR/static/pdf/.keep"
touch "$RELEASE_DIR/static/uploads/.keep"
touch "$RELEASE_DIR/print_inbox/.keep"
touch "$RELEASE_DIR/private/.keep"

# 5. Clean up any accidentally included sensitive files
echo "Cleaning sensitive data..."
rm -f "$RELEASE_DIR/.env"
rm -f "$RELEASE_DIR/qr.db"
rm -f "$RELEASE_DIR/qr.db-*"
find "$RELEASE_DIR" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
find "$RELEASE_DIR" -name "*.pyc" -delete 2>/dev/null || true
find "$RELEASE_DIR" -name ".pytest_cache" -type d -exec rm -rf {} + 2>/dev/null || true
find "$RELEASE_DIR" -name ".venv" -type d -exec rm -rf {} + 2>/dev/null || true
find "$RELEASE_DIR" -name "venv" -type d -exec rm -rf {} + 2>/dev/null || true

# Remove test and sample directories (not needed for production)
rm -rf "$RELEASE_DIR/tests" 2>/dev/null || true
rm -rf "$RELEASE_DIR/sample_photos" 2>/dev/null || true

# Remove private directory contents (contains sensitive PDFs)
rm -rf "$RELEASE_DIR/private/"*.pdf 2>/dev/null || true

# Remove runtime-generated directories
rm -rf "$RELEASE_DIR/static/generated" 2>/dev/null || true

# Remove legacy static assets
rm -rf "$RELEASE_DIR/static/pdf/"*.pdf 2>/dev/null || true
rm -rf "$RELEASE_DIR/static/signs/"*.png 2>/dev/null || true
rm -rf "$RELEASE_DIR/static/uploads/"*.jpg 2>/dev/null || true
rm -rf "$RELEASE_DIR/static/uploads/"*.png 2>/dev/null || true
rm -rf "$RELEASE_DIR/print_inbox/"*.pdf 2>/dev/null || true

# Remove releases directory (avoid nesting)
rm -rf "$RELEASE_DIR/releases" 2>/dev/null || true

# 6. Create tarball
echo "Creating archive..."
tar -czf "$ARCHIVE_NAME" -C "$RELEASE_DIR" .

echo ""
echo "✅ Release package created: $ARCHIVE_NAME"
echo "📦 Size: $(du -h $ARCHIVE_NAME | cut -f1)"
echo ""
echo "Verification - Files that should NOT be in release:"
tar -tzf "$ARCHIVE_NAME" | grep -E '(\.env$|qr\.db|\.pyc|__pycache__|\.venv|venv/|tests/|sample_photos/|\.pytest_cache)' || echo "  ✓ No sensitive/test files found"
echo ""
echo "Next steps:"
echo "1. Copy to server: scp $ARCHIVE_NAME user@server:/path/"
echo "2. Extract on server: tar -xzf $ARCHIVE_NAME"
echo "3. Create .env from .env.example"
echo "4. Run: pip-sync requirements.txt requirements-dev.txt"
echo "5. Follow DEPLOYMENT.md"
