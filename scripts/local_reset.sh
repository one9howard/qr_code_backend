#!/bin/bash
# Reset QR Code Business App Data
# Removes database, generated files, and runtime data for fresh start

echo -e "\033[0;36m=== QR Code App Reset ===\033[0m"
echo ""

# Configuration
DB_FILE="qr.db"
GENERATED_DIRS=(
    "static/qr"
    "static/signs"
    "static/pdf"
    "static/uploads"
    "static/generated"
    "private"
    "print_inbox"
    "releases"
    "logs"
)

# 1. Delete Database
echo -e "\033[0;33mChecking database...\033[0m"
if [ -f "$DB_FILE" ]; then
    rm -f "$DB_FILE" "$DB_FILE-journal" "$DB_FILE-wal" "$DB_FILE-shm" 2>/dev/null
    echo -e "\033[0;32m  Database ($DB_FILE) deleted.\033[0m"
else
    echo -e "\033[0;90m  Database ($DB_FILE) not found.\033[0m"
fi

# 2. Clear Generated Assets
echo ""
read -p "Delete all generated files (QRs, PDFs, uploads, releases)? (y/n) " response
if [[ "$response" =~ ^[Yy]$ ]]; then
    for path in "${GENERATED_DIRS[@]}"; do
        if [ -d "$path" ]; then
            find "$path" -type f -delete 2>/dev/null
            echo -e "\033[0;32m  Cleared: $path\033[0m"
        fi
    done
fi

# 3. Optionally remove virtual environment
echo ""
read -p "Delete virtual environment (.venv)? This requires reinstall. (y/n) " response
if [[ "$response" =~ ^[Yy]$ ]]; then
    if [ -d ".venv" ]; then
        rm -rf ".venv"
        echo -e "\033[0;32m  Virtual environment deleted.\033[0m"
        echo -e "\033[0;33m  Run: python3 -m venv .venv && source .venv/bin/activate\033[0m"
        echo -e "\033[0;33m       pip install pip-tools && pip-sync requirements.txt requirements-dev.txt\033[0m"
    else
        echo -e "\033[0;90m  .venv not found.\033[0m"
    fi
fi

echo ""
echo -e "\033[0;36m=== Reset Complete ===\033[0m"
echo "Restart the application to recreate the database."
