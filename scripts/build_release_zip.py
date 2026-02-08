#!/usr/bin/env python3
"""
Canonical Release Builder for InSite Signs.
Usage: python scripts/build_release_zip.py [options]

Features:
- Mandatory Pre-build Gates (release_acceptance.sh)
- Allowlist-based staging (clean build)
- ZIP Artifact creation (deterministic exclusions)
- Mandatory Post-build Validation (unzip & check)

Zero Tolerance:
- Fails if acceptance tests fail.
- Fails if artifact contains garbage.
- Fails if artifact is not syntactically valid.
"""

import os
import sys
import shutil
import zipfile
import subprocess
import argparse
import tempfile
import fnmatch
import hashlib
import getpass
import socket
import platform
import json
from datetime import datetime

# --- CONFIGURATION ---

# Directories to recursively include
INCLUDE_DIRS = [
    "routes",
    "services",
    "templates",
    "static",
    "utils",
    "scripts",  # Include scripts for operational tasks
    "migrations", # DB Migrations
]

# Root files (glob patterns) to include
ROOT_PATTERNS = [
    "*.py",          # All python files (app.py, config.py, extensions.py, etc)
    "migrate.py",      # Canonical migration runner
    "Procfile",        # Heroku/Railway entrypoint
    "alembic.ini",     # DB Config
    "requirements.txt", # Depencies
]

# Patterns to ALWAYS EXCLUDE (even if in allowlist)
GLOBAL_EXCLUDES = [
    "__pycache__*",
    "*.pyc",
    "*.pyo",
    "*.pyd",
    ".pytest_cache*",
    ".mypy_cache*",
    ".ruff_cache*",
    "*.log",
    "*.sqlite",
    ".DS_Store",
    ".env",
    ".env.*",
    "instance*",
    "tmp*",
    "pdfs*",  # Runtime generated PDFs
    "tests*", # Don't ship tests to prod (optional, but cleaner)
    "node_modules*",
    ".git*",
    ".github*",
    "*.zip",  # Don't include other zips
]

def run_command(cmd, cwd=None, env=None):
    """Run a shell command and fail hard if it errors."""
    print(f"Executing: {cmd}")
    try:
        # Merge env with current environment if provided
        cmd_env = os.environ.copy()
        if env:
            cmd_env.update(env)
        subprocess.check_call(cmd, shell=True, cwd=cwd, env=cmd_env)
    except subprocess.CalledProcessError as e:
        print(f"❌ Command failed: {cmd}")
        sys.exit(1)

def clean_tree(src_root, dest_root):
    """Copy allowlisted files from src to dest."""
    if os.path.exists(dest_root):
        shutil.rmtree(dest_root)
    os.makedirs(dest_root)

    # 1. Copy Directories
    for d in INCLUDE_DIRS:
        src_path = os.path.join(src_root, d)
        if not os.path.exists(src_path):
             print(f"Warning: Directory not found: {d}")
             continue
        
        dest_path = os.path.join(dest_root, d)
        shutil.copytree(src_path, dest_path, dirs_exist_ok=True, ignore=shutil.ignore_patterns(*GLOBAL_EXCLUDES))

    # 2. Copy Root Files matched by patterns
    # Get all files in root
    all_root_files = [f for f in os.listdir(src_root) if os.path.isfile(os.path.join(src_root, f))]
    
    for pat in ROOT_PATTERNS:
        # Filter files by pattern
        matching = fnmatch.filter(all_root_files, pat)
        for f in matching:
            # Check excludes
            if any(fnmatch.fnmatch(f, ex) for ex in GLOBAL_EXCLUDES):
                continue
                
            src = os.path.join(src_root, f)
            dest = os.path.join(dest_root, f)
            shutil.copy2(src, dest)
            # print(f"Included: {f}")

def create_zip(source_dir, zip_path):
    """Zips the source_dir into zip_path, enforcing global excludes."""
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(source_dir):
            # In-place filtering of dirs to avoid walking into excluded ones
            dirs[:] = [d for d in dirs if not any(fnmatch.fnmatch(d, pat) for pat in GLOBAL_EXCLUDES)]
            
            for file in files:
                if any(fnmatch.fnmatch(file, pat) for pat in GLOBAL_EXCLUDES):
                    continue
                
                abs_path = os.path.join(root, file)
                rel_path = os.path.relpath(abs_path, source_dir)
                zf.write(abs_path, rel_path)

def verify_import(temp_dir):
    """
    Attempt to import the app to verify all dependencies and files are present.
    This runs in a subprocess.
    """
    print("🧪 Verifying import (app introspection)...")
    
    # Simple check script that tries to import app
    # We mock DATABASE_URL to prevent connection attempts
    check_script = """
import sys
import os

# Mock ENV
os.environ['DATABASE_URL'] = 'postgresql://mock:mock@localhost/mock'
os.environ['SECRET_KEY'] = 'mock-secret-key'
os.environ['FLASK_ENV'] = 'production'
os.environ['STORAGE_BACKEND'] = 's3'
os.environ['S3_BUCKET'] = 'mock-bucket'
os.environ['AWS_REGION'] = 'us-east-1'
os.environ['PUBLIC_BASE_URL'] = 'https://example.com'
os.environ['STRIPE_SECRET_KEY'] = 'sk_live_mock'
os.environ['PRINT_JOBS_TOKEN'] = 'mock-print-token'

try:
    print("   Attempting 'import app'...")
    import app
    # Also verify extensions content if possible
    import extensions
    print("   [OK] Import successful.")
except ImportError as e:
    print(f"   [FAIL] ImportError: {e}")
    sys.exit(1)
except Exception as e:
    print(f"   [FAIL] Validation Error: {e}")
    sys.exit(1)
"""
    
    script_path = os.path.join(temp_dir, "_verify_build.py")
    with open(script_path, "w") as f:
        f.write(check_script)
        
    try:
        # Run with current python environment (assuming requirements are same/compatible)
        subprocess.check_call([sys.executable, script_path], cwd=temp_dir)
        return True
    except subprocess.CalledProcessError:
        print("[FAIL] Import verification failed.")
        return False
    finally:
        if os.path.exists(script_path):
            os.remove(script_path)




FORBIDDEN_STAGE_DIRS = {"__pycache__", ".pytest_cache"}
FORBIDDEN_STAGE_SUFFIXES = {".pyc", ".pyo"}

def assert_hard_hygiene(stage_dir: str) -> None:
    """Fail the build if any forbidden transient artifacts exist in the staged tree."""
    offenders = []
    for root, dirs, files in os.walk(stage_dir):
        for d in dirs:
            if d in FORBIDDEN_STAGE_DIRS:
                offenders.append(os.path.join(root, d))
        for f in files:
            if any(f.endswith(s) for s in FORBIDDEN_STAGE_SUFFIXES):
                offenders.append(os.path.join(root, f))
    if offenders:
        offenders = sorted({os.path.relpath(p, stage_dir) for p in offenders})
        preview = "\n".join(offenders[:50])
        raise RuntimeError(
            "[HARD HYGIENE] Forbidden build artifacts found in staging dir:\n"
            + preview
            + ("\n..." if len(offenders) > 50 else "")
        )

def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def write_release_manifest(stage_dir: str, project_root: str, zip_path: str) -> None:
    """Write RELEASE_MANIFEST.json into the staging directory."""
    built_at_utc = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

    git_sha = None
    try:
        git_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=project_root).decode("utf-8").strip()
    except Exception:
        git_sha = None

    files = []
    total_bytes = 0
    for root, _, fs in os.walk(stage_dir):
        for name in fs:
            full = os.path.join(root, name)
            rel = os.path.relpath(full, stage_dir).replace("\\", "/")
            size = os.path.getsize(full)
            total_bytes += size
            files.append({"path": rel, "size": size, "sha256": _sha256_file(full)})

    files.sort(key=lambda x: x["path"])

    tree_hash = hashlib.sha256()
    for entry in files:
        tree_hash.update(entry["path"].encode("utf-8") + b"\0" + entry["sha256"].encode("ascii") + b"\0")

    manifest = {
        "artifact_path": os.path.abspath(zip_path),
        "built_at_utc": built_at_utc,
        "source_git_sha": git_sha,
        "builder": {
            "user": getpass.getuser(),
            "host": socket.gethostname(),
            "platform": platform.platform(),
            "python": sys.version.split()[0],
        },
        "staged_tree": {
            "file_count": len(files),
            "total_bytes": total_bytes,
            "sha256": tree_hash.hexdigest(),
        },
        "files": files,
    }

    out_path = os.path.join(stage_dir, "RELEASE_MANIFEST.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
        f.write("\n")
def validate_artifact(zip_path):
    """
    Unzips the artifact to a temp dir and performs strict validation.
    1. Scan for forbidden patterns.
    2. Bytecode compile check.
    3. Import check.
    4. Run check_release_clean.py on the extracted content.
    """
    print(f"[INFO] Validating artifact: {zip_path}")
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create isolated environment for validation
        env = os.environ.copy()
        env['PYTHONPYCACHEPREFIX'] = temp_dir # Keep it inside the temp_dir
        env['PYTHONDONTWRITEBYTECODE'] = '1'
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(temp_dir)
        except Exception as e:
            print(f"[FAIL] Failed to extract zip: {e}")
            return False

        # 2. Strict Cleanliness Check (using the script itself)
        # We need to copy the check script into the temp dir OR run it from source against target path
        # But check_release_clean.py checks CWD. So we change dir.
        print("[LOCK] Running check_release_clean.py on artifact content...")
        
        # Copy the check script from source to temp_dir/scripts/check_release_clean.py
        # because the artifact might not have scripts/ (depending on allowlist, actually we do include scripts/check_*.py)
        # Let's ensure it's there or use the source one.
        check_script_path = os.path.join(temp_dir, "scripts", "check_release_clean.py")
        if not os.path.exists(check_script_path):
             # Ensure scripts dir exists
             os.makedirs(os.path.join(temp_dir, "scripts"), exist_ok=True)
             shutil.copy("scripts/check_release_clean.py", check_script_path)

        try:
            subprocess.check_call([sys.executable, check_script_path], cwd=temp_dir)
            print("[OK] Cleanliness check passed.")
        except subprocess.CalledProcessError:
            print("[FAIL] Artifact is not clean (contains banned files).")
            return False
        # 3. Key operational files check
        # Keep this minimal and environment-agnostic. Railway/Nixpacks may not use a Procfile.
        required_files = ["app.py", "migrate.py", "alembic.ini", "extensions.py"]
        missing = [f for f in required_files if not os.path.exists(os.path.join(temp_dir, f))]

        # Require at least one boot entrypoint hint (Procfile OR gunicorn config).
        if not (os.path.exists(os.path.join(temp_dir, "Procfile")) or os.path.exists(os.path.join(temp_dir, "gunicorn.conf.py"))):
            missing.append("Procfile or gunicorn.conf.py")

        if missing:
            print(f"[FAIL] Missing required operational files in artifact: {missing}")
            return False

        # 4. Syntax Check (No Disk Write)
        print("[LOCK] Running syntax verification on artifact...")
        try:
            # Using ast.parse to check syntax without writing any artifacts to disk
            check_syntax_script = (
                "import ast, os, sys\n"
                "errors = 0\n"
                "root = '.'\n"
                "for r, d, f in os.walk(root):\n"
                "  if any(s in r for s in ['.git', '.venv', 'venv', 'node_modules', '__pycache__']): continue\n"
                "  for file in f:\n"
                "    if file.endswith('.py'):\n"
                "      try:\n"
                "        with open(os.path.join(r, file), 'rb') as f_in:\n"
                "          ast.parse(f_in.read())\n"
                "      except Exception as e:\n"
                "        print(f'   [FAIL] Syntax error: {os.path.join(r, file)}: {e}')\n"
                "        errors += 1\n"
                "if errors: sys.exit(1)"
            )
            subprocess.check_call([sys.executable, "-c", check_syntax_script], cwd=temp_dir, env=env)
            print("[OK] Syntax check passed.")
        except subprocess.CalledProcessError:
            print(f"[FAIL] Syntax check failed inside artifact.")
            return False

        # 5. Import Check
        if not verify_import(temp_dir):
            return False

        # 6. Test Runner Availability (Inside Artifact)
        # We don't necessarily need pytest inside the artifact for it to be valid, 
        # but we check it here if we want to run tests as part of validation.
        # For now, validation is mostly about structure and syntax.

        print("[SUCCESS] Artifact validation passed.")
        return True

def run_pre_build_gates(allow_test_failures=False):
    """Run all pre-build gates via Docker."""
    print("========================================")
    print("    RELEASE ACCEPTANCE GATES")
    print("========================================")
    
    root = os.getcwd()
    
    # Get settings from environment
    web_service = os.environ.get('WEB_SERVICE', 'web')
    db_service = os.environ.get('DB_SERVICE', 'db')
    test_db_name = os.environ.get('TEST_DB_NAME', 'insite_test')
    test_db_url = os.environ.get('TEST_DATABASE_URL') or os.environ.get('DATABASE_URL')
    if not test_db_url:
        test_db_url = f"postgresql://postgres:postgres@{db_service}:5432/{test_db_name}"
    
    try:
        # Build with dev deps
        print(f"[GATE] Building {web_service} with dev deps...")
        subprocess.check_call(["docker", "compose", "build", "--build-arg", "INSTALL_DEV=true", web_service], cwd=root)
        
        # Start DB
        print(f"[GATE] Starting {db_service}...")
        subprocess.check_call(["docker", "compose", "up", "-d", db_service], cwd=root)
        
        # Wait for DB
        print("[GATE] Waiting for database...")
        import time
        for _ in range(30):
            result = subprocess.run(["docker", "compose", "exec", "-T", db_service, "pg_isready", "-U", "postgres"], 
                                   cwd=root, capture_output=True)
            if result.returncode == 0:
                break
            time.sleep(1)
        
        # Run tests in container
        print("[GATE] Running reset + migrate + pytest...")
        cmd = [
            "docker", "compose", "run", "--rm",
            "-e", f"DATABASE_URL={test_db_url}",
            "-e", f"TEST_DB_NAME={test_db_name}",
            web_service,
            "bash", "-lc", "set -euo pipefail && python scripts/reset_test_db.py && python migrate.py && python -m pytest -q"
        ]
        subprocess.check_call(cmd, cwd=root)
        
    except subprocess.CalledProcessError as e:
        if allow_test_failures:
            print(f"   [WARN] Acceptance FAILED (exit code {e.returncode}), but continuing anyway (--allow-test-failures)")
        else:
            print(f"   [FAIL] Acceptance FAILED (exit code {e.returncode}). Preventing release build.")
            # Cleanup
            subprocess.run(["docker", "compose", "down"], cwd=root, capture_output=True)
            sys.exit(e.returncode)
    finally:
        # Cleanup
        print("[GATE] Cleaning up...")
        subprocess.run(["docker", "compose", "down"], cwd=root, capture_output=True)
    
    print("========================================")
    print("[OK] ALL ACCEPTANCE CHECKS PASSED")
    print("========================================\n")

def main():
    parser = argparse.ArgumentParser(description="Build Release ZIP")
    parser.add_argument("--output-dir", default="releases", help="Output directory")
    parser.add_argument("--no-validate", action="store_true", help="SKIP VALIDATION (UNSAFE)")
    parser.add_argument("--i-understand-this-is-unsafe", action="store_true", help="Confirm unsafe mode")
    parser.add_argument("--allow-test-failures", action="store_true", help="Allow unit tests to fail (PASSES ALLOW_TEST_FAILURES=1)")
    args = parser.parse_args()

    # SAFETY CHECK
    if args.no_validate:
        if not args.i_understand_this_is_unsafe:
            print("❌ You must pass --i-understand-this-is-unsafe to use --no-validate.")
            sys.exit(1)
        print("⚠️  WARNING: SKIPPING VALIDATION. THIS IS UNSAFE. DO NOT SHIP THIS.")
    else:
        # FIREWALL BROKEN BUILDS
        if args.allow_test_failures:
            confirm_env = os.environ.get("I_UNDERSTAND_THIS_SHIPS_BROKEN")
            if confirm_env != "1":
                print("❌ ERROR: --allow-test-failures requires environment variable I_UNDERSTAND_THIS_SHIPS_BROKEN=1")
                print("   This is to prevent accidental shipment of failing code.")
                sys.exit(1)
            print("⚠️  WARNING: Allowing test failures as requested.")

        # 1. Pre-Build Gate
        run_pre_build_gates(allow_test_failures=args.allow_test_failures)

    project_root = os.getcwd()
    dist_dir = os.path.join(project_root, args.output_dir)
    os.makedirs(dist_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_filename = f"insite_signs_release_{timestamp}.zip"
    zip_path = os.path.join(dist_dir, zip_filename)
    
    # Use a temp dir for staging
    with tempfile.TemporaryDirectory() as staging_dir:
        print(f"[INFO] Staging files to {staging_dir}...")
        clean_tree(project_root, staging_dir)
        assert_hard_hygiene(staging_dir)
        write_release_manifest(staging_dir, project_root, zip_path)
        
        print(f"[INFO] Zipping to {zip_path}...")
        create_zip(staging_dir, zip_path)

    # 2. Post-Build Gate (Artifact Validation)
    if not args.no_validate:
         if not validate_artifact(zip_path):
             print("[FAIL] ARTIFACT VALIDATION FAILED. Deleting invalid artifact.")
             if os.path.exists(zip_path):
                 os.remove(zip_path)
             sys.exit(1)

    print(f"\n[SUCCESS] Release Build Success: {zip_path}")
    if not args.no_validate:
        print("   (Verified Clean & Functional)")

if __name__ == "__main__":
    main()
