#!/usr/bin/env python3
"""
Check availability of critical components for release.
"""
import os
import sys

def check_release_clean():
    errors = []
    
    # 1. Bytecode check
    # 1. Bytecode check
    for root, dirs, files in os.walk("."):
        if "__pycache__" in dirs:
            errors.append(f"[DIRTY] Found __pycache__ in {root}")
        for f in files:
            if f.endswith(".pyc"):
                errors.append(f"[DIRTY] Found .pyc file: {os.path.join(root, f)}")

    # 1.5. Forbidden Runtime Artifacts Check
    # Directories like 'pdfs' and 'tmp' are allowed to exist (e.g. for mount points)
    # but should not contain actual artifacts in a clean release.
    for runtime_dir in ["pdfs", "tmp"]:
        if os.path.exists(runtime_dir) and os.path.isdir(runtime_dir):
            # Check content
            contents = os.listdir(runtime_dir)
            # Allow empty or just .gitkeep
            artifacts = [c for c in contents if c != ".gitkeep"]
            if artifacts:
                 errors.append(f"[DIRTY] Runtime artifacts found in {runtime_dir}/: {artifacts}")

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
