#!/usr/bin/env python3
"""
Check availability of critical components for release.
"""
import os
import sys

def check_release_clean():
    errors = []
    
    # 1. Bytecode check
    for root, dirs, files in os.walk("."):
        if "__pycache__" in dirs:
            errors.append(f"[DIRTY] Found __pycache__ in {root}")
        for f in files:
            if f.endswith(".pyc"):
                errors.append(f"[DIRTY] Found .pyc file: {os.path.join(root, f)}")

    # 2. Critical Scripts Existence
    required_scripts = [
        "scripts/async_worker.py",
        "scripts/wait_for_db.py"
    ]
    for s in required_scripts:
        if not os.path.exists(s):
            errors.append(f"[MISSING] Required script not found: {s}")

    # 3. Docker Compose Sanity
    try:
        with open("docker-compose.yml", "r") as f:
            content = f.read()
            if "scripts/async_worker.py" not in content:
                errors.append("[CONFIG] docker-compose.yml does not reference scripts/async_worker.py")
            if "wait_for_db.py" not in content:
                errors.append("[CONFIG] docker-compose.yml does not reference wait_for_db.py")
    except FileNotFoundError:
        errors.append("[MISSING] docker-compose.yml not found")

    if errors:
        print("FAILURE: Release check failed.")
        for e in errors:
            print(e)
        sys.exit(1)
        
    print("SUCCESS: Release check passed. Clean and ready.")

if __name__ == "__main__":
    check_release_clean()
