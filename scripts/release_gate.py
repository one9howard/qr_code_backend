#!/usr/bin/env python3
import os
import sys
import subprocess

sys.dont_write_bytecode = True
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

def _normalize_stage(raw):
    raw = (raw or "").strip().lower()
    if raw in {"prod", "production"}:
        return "production"
    if raw in {"stage", "staging"}:
        return "staging"
    if raw in {"test", "testing"}:
        return "test"
    return "dev"

def check_forbidden_files():
    forbidden_exact = ["dump.sql", "dump.wkr"]
    found = []
    tracked_files = set()

    # Treat transient local bytecode as noise, but still catch truly committed artifacts.
    try:
        result = subprocess.run(
            ["git", "ls-files"],
            capture_output=True,
            text=True,
            check=False,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        )
        if result.returncode == 0:
            tracked_files = {line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()}
    except Exception:
        tracked_files = set()
    
    for root, dirs, files in os.walk("."):
        # Prune known safe dirs
        if ".git" in dirs: dirs.remove(".git")
        if "venv" in dirs: dirs.remove("venv")
        if "node_modules" in dirs: dirs.remove("node_modules")
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        
        # Check files
        for f in files:
            rel = os.path.relpath(os.path.join(root, f), ".").replace("\\", "/")
            is_forbidden = False
            if f in forbidden_exact: is_forbidden = True
            elif f.endswith(".dump"): is_forbidden = True
            elif f.endswith(".pyc"):
                # Only fail if bytecode artifacts are actually committed.
                is_forbidden = rel in tracked_files if tracked_files else True
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
    stage = _normalize_stage(os.getenv("APP_STAGE", "dev"))
    if stage not in {"staging", "production"}:
        return True

    pb_url = (os.getenv("PUBLIC_BASE_URL") or "").strip()
    if not pb_url:
        print(f"CRITICAL FAILURE: PUBLIC_BASE_URL not set in {stage}.")
        return False

    lower_pb = pb_url.lower()
    if not lower_pb.startswith("https://"):
        print(f"CRITICAL FAILURE: PUBLIC_BASE_URL '{pb_url}' must use https in {stage}.")
        return False
    if "localhost" in lower_pb or "127.0.0.1" in lower_pb:
        print(f"CRITICAL FAILURE: PUBLIC_BASE_URL '{pb_url}' is unsafe for {stage}.")
        return False
    if stage == "production" and "staging" in lower_pb:
        print(f"CRITICAL FAILURE: PUBLIC_BASE_URL '{pb_url}' is unsafe for production.")
        return False

    stripe_secret = os.getenv("STRIPE_SECRET_KEY", "")
    if stage == "staging" and stripe_secret.startswith("sk_live_"):
        print("CRITICAL FAILURE: Live Stripe secret key is forbidden in staging.")
        return False
    if stage == "production" and stripe_secret.startswith("sk_test_"):
        print("CRITICAL FAILURE: Test Stripe secret key is forbidden in production.")
        return False
    return True

def check_specs_sync():
    """Run SPECS sync check via subprocess."""
    import subprocess
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        ["python", "scripts/check_specs_sync.py"],
        capture_output=True,
        text=True,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        env=env,
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
        result = subprocess.run(
            ["bash", "scripts/release_acceptance.sh"],
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        )
        if result.returncode != 0:
            print("[Release Gate] FAILED: Acceptance tests did not pass.")
            sys.exit(1)
    else:
        print(f"[Release Gate] WARNING: Canonical runner not found: {acceptance_script}")

    print("[Release Gate] PASSED.")
    sys.exit(0)
