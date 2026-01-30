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

if __name__ == "__main__":
    print("[Release Gate] Running safety checks...")
    success = True
    if not check_forbidden_files(): success = False
    if not check_fonts(): success = False
    if not check_config(): success = False
    
    if not success:
        print("[Release Gate] FAILED.")
        sys.exit(1)
    
    print("[Release Gate] PASSED.")
    sys.exit(0)
