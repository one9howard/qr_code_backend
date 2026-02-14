#!/usr/bin/env python3
import os
import sys

def check_forbidden_files():
    forbidden_exact = ["dump.sql", "dump.wkr"]
    found = []
    
    for root, dirs, files in os.walk("."):
        # Prune known safe dirs
        if ".git" in dirs: dirs.remove(".git")
        if "venv" in dirs: dirs.remove("venv")
        if "node_modules" in dirs: dirs.remove("node_modules")
        
        # Check directories
        for d in dirs:
            if d == "__pycache__":
                found.append(os.path.join(root, d))
        
        # Check files
        for f in files:
            is_forbidden = False
            if f in forbidden_exact: is_forbidden = True
            elif f.endswith(".dump"): is_forbidden = True
            elif f.endswith(".pyc"): is_forbidden = True
            elif f.startswith("debug_") and (f.endswith(".json") or f.endswith(".html")):
                is_forbidden = True
            
            if is_forbidden:
                found.append(os.path.join(root, f))
                         
    if found:
        print("CRITICAL FAILURE: Forbidden artifacts found in repo:")
        for f in found: print(f"  - {f}")
        return False
    return True

def check_fonts():
    fonts_dir = "static/fonts"
    required = ["Inter-Regular.ttf", "Inter-Medium.ttf", "Inter-Bold.ttf"]
    missing = []
    for r in required:
        if not os.path.exists(os.path.join(fonts_dir, r)):
            missing.append(r)
    if missing:
        print(f"CRITICAL FAILURE: Missing required Inter fonts in {fonts_dir}:")
        for m in missing: print(f"  - {m}")
        return False
    return True

def check_config():
    # Only if FLASK_ENV is set to production
    if os.getenv("FLASK_ENV") == "production":
        pb_url = os.getenv("PUBLIC_BASE_URL")
        if not pb_url:
            print("CRITICAL FAILURE: PUBLIC_BASE_URL not set in production.")
            return False
        if "staging" in pb_url or "localhost" in pb_url:
            print(f"CRITICAL FAILURE: PUBLIC_BASE_URL '{pb_url}' is unsafe for production.")
            return False
    return True

def check_specs_sync():
    """Run SPECS sync check via subprocess."""
    import subprocess
    result = subprocess.run(
        ["python", "scripts/check_specs_sync.py"],
        capture_output=True,
        text=True,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    if result.returncode != 0:
        print("CRITICAL FAILURE: SPECS.md is out of sync.")
        print(result.stdout)
        print(result.stderr)
        return False
    print(result.stdout.strip())
    return True

if __name__ == "__main__":
    print("[Release Gate] Running safety checks...")

    success = True
    if not check_forbidden_files(): success = False
    if not check_fonts(): success = False
    if not check_config(): success = False
    if not check_specs_sync(): success = False

    if not success:
        print("[Release Gate] FAILED.")
        sys.exit(1)

    # Then run the canonical acceptance tests
    print("[Release Gate] Running acceptance tests...")
    import subprocess
    from pathlib import Path
    acceptance_script = Path(__file__).resolve().parent / "release_acceptance.sh"
    if acceptance_script.exists():
        # Convert Windows path to Unix-style for bash
        script_path = str(acceptance_script)
        if os.name == 'nt':
            script_path = script_path.replace('\\', '/')
            if len(script_path) >= 2 and script_path[1] == ':':
                script_path = '/' + script_path[0].lower() + script_path[2:]
        result = subprocess.run(["bash", script_path], cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if result.returncode != 0:
            print("[Release Gate] FAILED: Acceptance tests did not pass.")
            sys.exit(1)
    else:
        print(f"[Release Gate] WARNING: Canonical runner not found: {acceptance_script}")

    print("[Release Gate] PASSED.")
    sys.exit(0)
