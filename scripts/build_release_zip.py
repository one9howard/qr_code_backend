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

# Files/Dirs to explicitly INCLUDE in the build
ALLOWLIST = [
    "routes",
    "services",
    "templates",
    "static",
    "utils",
    "config.py",
    "constants.py",
    "database.py",
    "models.py",
    "app.py",
    "requirements.txt",
    "Procfile",
    "scripts",  # Include scripts for operational tasks
    "migrations", # DB Migrations
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

def run_command(cmd, cwd=None):
    """Run a shell command and fail hard if it errors."""
    print(f"Executing: {cmd}")
    try:
        subprocess.check_call(cmd, shell=True, cwd=cwd)
    except subprocess.CalledProcessError as e:
        print(f"❌ Command failed: {cmd}")
        sys.exit(1)

def clean_tree(src_root, dest_root):
    """Copy allowlisted files from src to dest."""
    if os.path.exists(dest_root):
        shutil.rmtree(dest_root)
    os.makedirs(dest_root)

    for item in ALLOWLIST:
        src_path = os.path.join(src_root, item)
        if not os.path.exists(src_path):
            print(f"Warning: Allowlisted item not found: {item}")
            continue
        
        dest_path = os.path.join(dest_root, item)
        if os.path.isdir(src_path):
            shutil.copytree(src_path, dest_path, dirs_exist_ok=True, ignore=shutil.ignore_patterns(*GLOBAL_EXCLUDES))
        else:
            shutil.copy2(src_path, dest_path)

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

def validate_artifact(zip_path):
    """
    Unzips the artifact to a temp dir and performs strict validation.
    1. Scan for forbidden patterns.
    2. Bytecode compile check.
    """
    print(f"🕵️ Validating artifact: {zip_path}")
    with tempfile.TemporaryDirectory() as temp_dir:
        # 1. Unzip
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(temp_dir)
        except Exception as e:
            print(f"❌ Failed to extract zip: {e}")
            return False

        # 2. Scan for forbidden
        failure = False
        for root, dirs, files in os.walk(temp_dir):
            for item in dirs + files:
                for pat in GLOBAL_EXCLUDES:
                    # Strip * for simple substring checks if needed, but fnmatch is best
                    if fnmatch.fnmatch(item, pat):
                        # Some patterns like __pycache__ might sneak in if copytree failed
                        print(f"❌ FORBIDDEN FILE FOUND IN ARTIFACT: {item} (Matches {pat})")
                        failure = True

        if failure:
            return False

        # 3. Syntax Check (compileall)
        print("running compileall on artifact...")
        try:
            subprocess.check_call(f"{sys.executable} -m compileall -q .", cwd=temp_dir, shell=True)
        except subprocess.CalledProcessError:
            print(f"❌ Syntax check failed inside artifact.")
            return False

        print("✅ Artifact validation passed.")
        return True

def main():
    parser = argparse.ArgumentParser(description="Build Release ZIP")
    parser.add_argument("--output-dir", default="releases", help="Output directory")
    parser.add_argument("--no-validate", action="store_true", help="SKIP VALIDATION (UNSAFE)")
    parser.add_argument("--i-understand-this-is-unsafe", action="store_true", help="Confirm unsafe mode")
    args = parser.parse_args()

    # SAFETY CHECK
    if args.no_validate:
        if not args.i_understand_this_is_unsafe:
            print("❌ You must pass --i-understand-this-is-unsafe to use --no-validate.")
            sys.exit(1)
        print("⚠️  WARNING: SKIPPING VALIDATION. THIS IS UNSAFE. DO NOT SHIP THIS.")
    else:
        # 1. Pre-Build Gate
        print("🔒 Running Pre-Build Gates...")
        # Assuming script is run from project root
        run_command("bash scripts/release_acceptance.sh")

    project_root = os.getcwd()
    dist_dir = os.path.join(project_root, args.output_dir)
    os.makedirs(dist_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_filename = f"insite_signs_release_{timestamp}.zip"
    zip_path = os.path.join(dist_dir, zip_filename)
    
    # Use a temp dir for staging
    with tempfile.TemporaryDirectory() as staging_dir:
        print(f"📂 Staging files to {staging_dir}...")
        clean_tree(project_root, staging_dir)
        
        print(f"📦 Zipping to {zip_path}...")
        create_zip(staging_dir, zip_path)

    # 2. Post-Build Gate (Artifact Validation)
    if not args.no_validate:
         if not validate_artifact(zip_path):
             print("❌ ARTIFACT VALIDATION FAILED. Deleting invalid artifact.")
             if os.path.exists(zip_path):
                 os.remove(zip_path)
             sys.exit(1)

    print(f"\n✨ Release Build Success: {zip_path}")
    if not args.no_validate:
        print("   (Verified Clean & Functional)")

if __name__ == "__main__":
    main()
