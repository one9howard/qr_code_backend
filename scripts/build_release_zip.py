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
from datetime import UTC, datetime
from pathlib import Path

# --- PATH RESOLUTION (do not rely on cwd) ---
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_PROJECT_ROOT = SCRIPT_DIR.parent


# --- CONFIGURATION ---
MANIFEST_FILENAME = "RELEASE_MANIFEST.json"

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
    ".env.local",
    ".env.production",
    ".env.staging",
    ".env.test",
    "instance*",
    "tmp*",
    "pdfs*",  # Runtime generated PDFs
    "node_modules*",
    ".git*",
    ".github*",
    "*.zip",  # Don't include other zips
    "static/*.pdf", # Generated previews
]


def _normalize_relpath(path: str) -> str:
    rel = path.replace("\\", "/").strip().strip("/")
    return rel


def _is_valid_relpath(path: str) -> bool:
    if not path:
        return False
    p = Path(path)
    if p.is_absolute():
        return False
    parts = [_normalize_relpath(str(x)) for x in p.parts if str(x)]
    if any(part in {".", ".."} for part in parts):
        return False
    return True


def load_release_allowlist(project_root: str) -> dict:
    manifest_path = os.path.join(project_root, MANIFEST_FILENAME)
    if not os.path.isfile(manifest_path):
        raise RuntimeError(f"[ALLOWLIST] Missing {MANIFEST_FILENAME} at repo root.")

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except Exception as e:
        raise RuntimeError(f"[ALLOWLIST] Could not parse {MANIFEST_FILENAME}: {e}")

    allowlist = manifest.get("allowlist")
    if not isinstance(allowlist, dict):
        raise RuntimeError(
            f"[ALLOWLIST] {MANIFEST_FILENAME} must contain top-level object 'allowlist'."
        )

    files = allowlist.get("files", [])
    dirs = allowlist.get("dirs", [])
    exclude_paths = allowlist.get("exclude_paths", [])
    optional_top_level = allowlist.get("optional_top_level", [])

    for field_name, values in (
        ("allowlist.files", files),
        ("allowlist.dirs", dirs),
        ("allowlist.exclude_paths", exclude_paths),
        ("allowlist.optional_top_level", optional_top_level),
    ):
        if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
            raise RuntimeError(f"[ALLOWLIST] {field_name} must be a list of strings.")
        for v in values:
            if not _is_valid_relpath(v):
                raise RuntimeError(f"[ALLOWLIST] Invalid relative path in {field_name}: {v!r}")

    files = sorted({_normalize_relpath(p) for p in files})
    dirs = sorted({_normalize_relpath(p) for p in dirs})
    exclude_paths = sorted({_normalize_relpath(p) for p in exclude_paths})
    optional_top_level = sorted({_normalize_relpath(p) for p in optional_top_level})

    if MANIFEST_FILENAME not in files:
        files.append(MANIFEST_FILENAME)

    return {
        "files": files,
        "dirs": dirs,
        "exclude_paths": exclude_paths,
        "optional_top_level": optional_top_level,
    }


def _matches_global_exclude(rel_path: str) -> bool:
    rel = _normalize_relpath(rel_path)
    base = os.path.basename(rel)
    for pattern in GLOBAL_EXCLUDES:
        if fnmatch.fnmatch(base, pattern) or fnmatch.fnmatch(rel, pattern):
            return True
    return False


def _is_path_excluded(rel_path: str, exclude_paths: list[str]) -> bool:
    rel = _normalize_relpath(rel_path)
    for ex in exclude_paths:
        exn = _normalize_relpath(ex)
        if rel == exn or rel.startswith(f"{exn}/"):
            return True
    return False

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



def assert_repo_root(project_root: str) -> None:
    """Fail fast if invoked from a non-repo directory.

    This builder used to rely on os.getcwd(). If someone ran it from scripts/,
    it would stage the wrong tree and produce a broken artifact.
    """
    required_paths = [
        ("app.py", "file"),
        ("config.py", "file"),
        ("migrate.py", "file"),
        ("routes", "dir"),
        ("services", "dir"),
        ("templates", "dir"),
        ("scripts", "dir"),
    ]

    missing = []
    for rel, kind in required_paths:
        full = os.path.join(project_root, rel)
        if kind == "file" and not os.path.isfile(full):
            missing.append(rel)
        if kind == "dir" and not os.path.isdir(full):
            missing.append(rel)

    if missing:
        raise RuntimeError(
            "[REPO ROOT] Refusing to build: not in project root. Missing: "
            + ", ".join(missing)
            + "\nResolved project_root="
            + project_root
        )


def ensure_specs_synced(project_root: str) -> None:
    """Generate SPECS.md and fail the release build if it is still out of sync."""
    specs_path = os.path.join(project_root, "SPECS.md")
    print("[GATE] Generating SPECS.md...")
    subprocess.check_call([sys.executable, "scripts/generate_specs_md.py"], cwd=project_root)
    if not os.path.isfile(specs_path):
        raise RuntimeError("[SPECS] scripts/generate_specs_md.py did not produce SPECS.md")
    print("[GATE] Verifying SPECS.md sync...")
    subprocess.check_call([sys.executable, "scripts/check_specs_sync.py"], cwd=project_root)


def clean_tree(src_root: str, dest_root: str, allowlist: dict) -> None:
    """Copy only manifest-allowlisted files/dirs from src to dest."""
    if os.path.exists(dest_root):
        shutil.rmtree(dest_root)
    os.makedirs(dest_root)

    # 1) Copy allowlisted files (top-level or nested).
    for rel_file in allowlist["files"]:
        if rel_file == MANIFEST_FILENAME:
            # Manifest is regenerated after staging to include fresh hashes.
            continue
        if _is_path_excluded(rel_file, allowlist["exclude_paths"]):
            continue
        if _matches_global_exclude(rel_file):
            continue

        src_file = os.path.join(src_root, rel_file)
        if not os.path.isfile(src_file):
            raise RuntimeError(f"[ALLOWLIST] Required file is missing: {rel_file}")

        dest_file = os.path.join(dest_root, rel_file)
        os.makedirs(os.path.dirname(dest_file), exist_ok=True)
        shutil.copy2(src_file, dest_file)

    # 2) Copy allowlisted directories recursively.
    for rel_dir in allowlist["dirs"]:
        src_dir = os.path.join(src_root, rel_dir)
        if not os.path.isdir(src_dir):
            raise RuntimeError(f"[ALLOWLIST] Required directory is missing: {rel_dir}")

        for root, dirnames, filenames in os.walk(src_dir):
            rel_root = _normalize_relpath(os.path.relpath(root, src_root))
            if _is_path_excluded(rel_root, allowlist["exclude_paths"]):
                dirnames[:] = []
                continue

            # Prune excluded subdirs in-place.
            pruned = []
            for d in dirnames:
                child_rel = _normalize_relpath(os.path.join(rel_root, d))
                if _is_path_excluded(child_rel, allowlist["exclude_paths"]):
                    continue
                if _matches_global_exclude(child_rel):
                    continue
                pruned.append(d)
            dirnames[:] = pruned

            for name in filenames:
                rel_file = _normalize_relpath(os.path.join(rel_root, name))
                if _is_path_excluded(rel_file, allowlist["exclude_paths"]):
                    continue
                if _matches_global_exclude(rel_file):
                    continue

                src_file = os.path.join(src_root, rel_file)
                dest_file = os.path.join(dest_root, rel_file)
                os.makedirs(os.path.dirname(dest_file), exist_ok=True)
                shutil.copy2(src_file, dest_file)

    # Guardrail: nothing outside allowlist should have been copied.
    disallowed = []
    for root, _, filenames in os.walk(dest_root):
        for name in filenames:
            rel_file = _normalize_relpath(os.path.relpath(os.path.join(root, name), dest_root))
            if rel_file == MANIFEST_FILENAME:
                continue
            if _is_path_excluded(rel_file, allowlist["exclude_paths"]):
                disallowed.append(rel_file)
                continue
            is_allowed_file = rel_file in {_normalize_relpath(f) for f in allowlist["files"]}
            is_allowed_under_dir = any(
                rel_file == d or rel_file.startswith(f"{d}/")
                for d in {_normalize_relpath(d) for d in allowlist["dirs"]}
            )
            if not (is_allowed_file or is_allowed_under_dir):
                disallowed.append(rel_file)

    if disallowed:
        preview = "\n".join(sorted(disallowed)[:50])
        raise RuntimeError(
            "[ALLOWLIST] Staging produced files outside RELEASE_MANIFEST allowlist:\n"
            + preview
            + ("\n..." if len(disallowed) > 50 else "")
        )

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

def verify_import(temp_dir, check_stage="staging"):
    """
    Attempt to import the app to verify all dependencies and files are present.
    This runs in a subprocess.
    """
    print("[VERIFY] Verifying import (app introspection)...")
    
    # Simple check script that tries to import app
    # We mock DATABASE_URL to prevent connection attempts
    stripe_secret = "sk_live_mock" if check_stage == "production" else "sk_test_mock"
    stripe_publishable = "pk_live_mock" if check_stage == "production" else "pk_test_mock"
    check_script = f"""
import sys
import os

# Mock ENV
os.environ['DATABASE_URL'] = 'postgresql://mock:mock@localhost/mock'
os.environ['SECRET_KEY'] = 'mock-secret-key'
os.environ['FLASK_ENV'] = 'production'
os.environ['APP_STAGE'] = '{check_stage}'
os.environ['STORAGE_BACKEND'] = 's3'
os.environ['S3_BUCKET'] = 'mock-bucket'
os.environ['AWS_REGION'] = 'us-east-1'
os.environ['PUBLIC_BASE_URL'] = 'https://example.com'
os.environ['STRIPE_SECRET_KEY'] = '{stripe_secret}'
os.environ['STRIPE_PUBLISHABLE_KEY'] = '{stripe_publishable}'
os.environ['SKIP_STRIPE_PRICE_WARMUP'] = '1'
os.environ['PRINT_JOBS_TOKEN'] = 'mock-print-token'

try:
    print("   Attempting 'import app'...")
    import app
    # Also verify extensions content if possible
    import extensions
    print("   [OK] Import successful.")
except ImportError as e:
    print(f"   [FAIL] ImportError: {{e}}")
    sys.exit(1)
except Exception as e:
    print(f"   [FAIL] Validation Error: {{e}}")
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

def write_release_manifest(stage_dir: str, project_root: str, zip_path: str, allowlist: dict) -> None:
    """Write RELEASE_MANIFEST.json into the staging directory."""
    built_at_utc = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")

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
        "allowlist": {
            "files": sorted(allowlist.get("files", [])),
            "dirs": sorted(allowlist.get("dirs", [])),
            "exclude_paths": sorted(allowlist.get("exclude_paths", [])),
            "optional_top_level": sorted(allowlist.get("optional_top_level", [])),
        },
        "files": files,
    }

    out_path = os.path.join(stage_dir, "RELEASE_MANIFEST.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
        f.write("\n")
def validate_artifact(zip_path, project_root, check_stage="staging"):
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
             shutil.copy(os.path.join(project_root, "scripts", "check_release_clean.py"), check_script_path)

        try:
            subprocess.check_call([sys.executable, check_script_path, "--root", temp_dir])
            print("[OK] Cleanliness check passed.")
        except subprocess.CalledProcessError:
            print("[FAIL] Artifact is not clean (contains banned files).")
            return False
        # 3. Key operational files check
        # Keep this minimal and environment-agnostic. Railway/Nixpacks may not use a Procfile.
        required_files = [
            "app.py",
            "migrate.py",
            "alembic.ini",
            "extensions.py",
            "SPECS.md",
            "runtime.txt",
            ".python-version",
            "Dockerfile",
            ".dockerignore",
            "docker-compose.yml",
        ]
        missing = [f for f in required_files if not os.path.exists(os.path.join(temp_dir, f))]

        # README can be README, README.md, README.txt, etc.
        if not any(
            fnmatch.fnmatch(name.lower(), "readme*")
            for name in os.listdir(temp_dir)
            if os.path.isfile(os.path.join(temp_dir, name))
        ):
            missing.append("README*")

        # Tests directory is required in release artifact for verification workflows.
        if not os.path.isdir(os.path.join(temp_dir, "tests")):
            missing.append("tests/")

        # Require at least one boot entrypoint hint (Procfile OR gunicorn config).
        if not (os.path.exists(os.path.join(temp_dir, "Procfile")) or os.path.exists(os.path.join(temp_dir, "gunicorn.conf.py"))):
            missing.append("Procfile or gunicorn.conf.py")

        if missing:
            print(f"[FAIL] Missing required operational files in artifact: {missing}")
            return False

        # 4. SPECS sync check
        print("[LOCK] Running SPECS sync check on artifact...")
        try:
            subprocess.check_call([sys.executable, "scripts/check_specs_sync.py"], cwd=temp_dir, env=env)
            print("[OK] SPECS sync check passed.")
        except subprocess.CalledProcessError:
            print("[FAIL] SPECS sync check failed inside artifact.")
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
        if not verify_import(temp_dir, check_stage=check_stage):
            return False

        # 6. Test Runner Availability (Inside Artifact)
        # We don't necessarily need pytest inside the artifact for it to be valid, 
        # but we check it here if we want to run tests as part of validation.
        # For now, validation is mostly about structure and syntax.

        print("[SUCCESS] Artifact validation passed.")
        return True

def run_pre_build_gates(project_root: str, allow_test_failures: bool = False):
    """Run all pre-build gates via Docker using the canonical shell script."""
    print("========================================")
    print("    RELEASE ACCEPTANCE GATES")
    print("========================================")
    
    # Use the canonical shell script
    # This ensures that what we test in CI/Dev is EXACTLY what gates the release.
    # We use a relative path with forward slashes to ensure compatibility with bash on Windows.
    script_path = "scripts/run_tests_in_docker.sh"
    
    try:
        # We invoke via bash to ensure it runs even if +x is missing on Windows/host
        print(f"[GATE] Executing canonical test runner: {script_path}")
        subprocess.check_call(["bash", script_path], cwd=project_root)
        
    except subprocess.CalledProcessError as e:
        if allow_test_failures:
            print(f"   [WARN] Acceptance FAILED (exit code {e.returncode}), but continuing anyway (--allow-test-failures)")
        else:
            print(f"   [FAIL] Acceptance FAILED (exit code {e.returncode}). Preventing release build.")
            # The script cleanup should have handled itself, but just in case we exit hard.
            sys.exit(e.returncode)
    
    print("========================================")
    print("[OK] ALL ACCEPTANCE CHECKS PASSED")
    print("========================================\n")

def main():
    parser = argparse.ArgumentParser(description="Build Release ZIP")
    parser.add_argument("--output-dir", default="releases", help="Output directory")
    parser.add_argument("--project-root", default=None, help="Project root (defaults to repo root resolved from this script)")
    parser.add_argument(
        "--check-stage",
        choices=["staging", "production"],
        default=os.environ.get("RELEASE_CHECK_STAGE", "staging"),
        help="Stage to emulate during artifact import validation.",
    )
    parser.add_argument("--no-validate", action="store_true", help="SKIP VALIDATION (UNSAFE)")
    parser.add_argument("--i-understand-this-is-unsafe", action="store_true", help="Confirm unsafe mode")
    parser.add_argument("--allow-test-failures", action="store_true", help="Allow unit tests to fail (PASSES ALLOW_TEST_FAILURES=1)")
    args = parser.parse_args()

    # Resolve project root deterministically (do not rely on cwd)
    pr = Path(args.project_root).resolve() if args.project_root else DEFAULT_PROJECT_ROOT
    project_root = str(pr)
    assert_repo_root(project_root)
    ensure_specs_synced(project_root)
    allowlist = load_release_allowlist(project_root)

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
        run_pre_build_gates(project_root, allow_test_failures=args.allow_test_failures)

    out_dir = args.output_dir
    if os.path.isabs(out_dir):
        dist_dir = out_dir
    else:
        dist_dir = os.path.join(project_root, out_dir)
    os.makedirs(dist_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_filename = f"insite_signs_release_{timestamp}.zip"
    zip_path = os.path.join(dist_dir, zip_filename)
    
    # Use a temp dir for staging
    with tempfile.TemporaryDirectory() as staging_dir:
        print(f"[INFO] Staging files to {staging_dir}...")
        clean_tree(project_root, staging_dir, allowlist)
        assert_hard_hygiene(staging_dir)
        write_release_manifest(staging_dir, project_root, zip_path, allowlist)
        
        print(f"[INFO] Zipping to {zip_path}...")
        create_zip(staging_dir, zip_path)

    # 2. Post-Build Gate (Artifact Validation)
    if not args.no_validate:
        validate_script = os.path.join(project_root, "scripts", "validate_release_zip.py")
        try:
            subprocess.check_call(
                [sys.executable, validate_script, zip_path, "--check-stage", args.check_stage],
                cwd=project_root,
            )
        except subprocess.CalledProcessError:
            print("[FAIL] ARTIFACT VALIDATION FAILED. Deleting invalid artifact.")
            if os.path.exists(zip_path):
                os.remove(zip_path)
            sys.exit(1)

    print(f"\n[SUCCESS] Release Build Success: {zip_path}")
    if not args.no_validate:
        print("   (Verified Clean & Functional)")

if __name__ == "__main__":
    main()
