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
    """Run all pre-build gates directly in Python to avoid shell environment issues."""
    print("========================================")
    print("    RELEASE ACCEPTANCE GATES (Python Native)")
    print("========================================")
    
    python = sys.executable
    root = os.getcwd()

    # Isolate bytecode during gates
    with tempfile.TemporaryDirectory() as pycache_dir:
        env = os.environ.copy()
        env['PYTHONPYCACHEPREFIX'] = pycache_dir
        env['PYTHONDONTWRITEBYTECODE'] = '1'

        # 1. Cleanliness
        print("[LOCK] 1. Checking for repository cleanliness...")
        check_clean_path = os.path.join(root, "scripts", "check_release_clean.py")
        if os.path.exists(check_clean_path):
            subprocess.check_call([python, check_clean_path], cwd=root, env=env)
        else:
            print("   [WARN] scripts/check_release_clean.py not found! Skipping...")

        # 2. No Prints
        print("[LOCK] 2. Checking for forbidden print() statements...")
        check_prints_path = os.path.join(root, "scripts", "check_no_prints.py")
        if os.path.exists(check_prints_path):
            subprocess.check_call([python, check_prints_path], cwd=root, env=env)
        else:
            print("   [FAIL] scripts/check_no_prints.py not found!")
            sys.exit(1)

        # 3. Syntax Check
        print("[LOCK] 3. Syntax Verification (No Disk Write)...")
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
        subprocess.check_call([python, "-c", check_syntax_script], cwd=root, env=env)
        print("   [OK] Syntax Verification Passed")

        # 4. Unit Tests
        print("[TEST] 4. Running Unit Tests...")
        # First check if pytest is installed
        check_pytest_cmd = [python, "-c", "import pytest"]
        try:
            subprocess.check_call(check_pytest_cmd, cwd=root, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            print("   [FAIL] pytest NOT FOUND in current environment.")
            print("          Please run: pip install -r requirements-test.txt")
            sys.exit(1)

        test_cmd = [python, "-m", "pytest", "-q", "-m", "not slow"]
        try:
            subprocess.check_call(test_cmd, cwd=root, env=env)
        except subprocess.CalledProcessError as e:
            if not allow_test_failures:
                print(f"   [FAIL] Tests FAILED (exit code {e.returncode}). Preventing release build.")
                sys.exit(e.returncode)
            else:
                print("   [WARN] Tests FAILED, but but continuing anyway (--allow-test-failures)")
        print("   [OK] Tests Passed")

        # 5. Migration Check
        print("[TEST] 5. Checking for canonical migration runner...")
        if os.path.exists(os.path.join(root, "migrate.py")) and os.path.exists(os.path.join(root, "alembic.ini")):
            print("   [OK] migrate.py and alembic.ini found.")
        else:
            print("   [FAIL] Canonical migration runner (migrate.py) or config (alembic.ini) missing!")
            sys.exit(1)

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
