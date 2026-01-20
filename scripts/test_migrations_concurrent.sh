#!/bin/bash
# Test valid concurrency for SQLite migrations
# This script spawns 10 parallel processes attempting to run migrate.py
# If locking works, they should run serially (or wait) and succeed.
# If locking fails, we might see "database locked" errors or race conditions.

# Ensure we are in the project root
cd "$(dirname "$0")/.."

echo "[Test] Starting 10 concurrent migration attempts..."

for i in {1..10}; do
   python3 migrate.py &
   pids[${i}]=$!
done

# Wait for all
FAIL=0
for pid in ${pids[*]}; do
    wait $pid
    if [ $? -ne 0 ]; then
        FAIL=1
    fi
done

if [ $FAIL -eq 0 ]; then
    echo "[Test] ALL migrations completed successfully. Locking is working."
else
    echo "[Test] FAILURE in concurrent migrations."
    exit 1
fi
