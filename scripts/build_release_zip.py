#!/usr/bin/env python3
"""
Build a clean release zip excluding secrets, generated files, and runtime data.

Profiles:
  - prod  : deploy-oriented zip (excludes tests/CI by default, ships required runtime/ops scripts)
  - review: engineering/review zip (includes scripts/, tests/, .github/)

Usage:
  python scripts/build_release_zip.py --profile prod
  python scripts/build_release_zip.py --profile review

Output:
  releases/insite_signs_release_<timestamp>.zip
  releases/insite_signs_release.zip  (latest copy)
"""
import os
import zipfile
import fnmatch
import argparse
import shutil
from datetime import datetime


def get_profile_config(profile: str):
    """
    Return (exclude_patterns, include_overrides, forbidden_patterns) for a given profile.

    - exclude_patterns: files/dirs omitted from the zip
    - include_overrides: exact file paths that must be included even if excluded by patterns
    - forbidden_patterns: if anything matching appears in the zip, the build fails
    """
    if profile not in ("prod", "review"):
        raise ValueError(f"Unknown profile '{profile}'. Use 'prod' or 'review'.")

    # Common excludes (always)
    common_excludes = [
        # Version control
        ".git",
        ".git/*",

        # Secrets and env files (except .env.example)
        ".env",
        ".env.*",

        # Database files
        "*.db",
        "*.db-journal",
        "*.db-wal",
        "*.db-shm",
        "qr.db",

        # Python cache
        "__pycache__",
        "*.pyc",
        "*.pyo",
        "*.pyd",
        ".pytest_cache",

        # Virtual environments
        "venv",
        ".venv",
        "env",

        # Private/runtime data
        "instance",
        "private",
        "print_inbox",
        "logs",

        # Generated static content
        "static/qr",
        "static/signs",
        "static/pdf",
        "static/uploads",
        "static/generated",

        # Release output (avoid nesting)
        # Release output (avoid nesting)
        "releases",
        "release",
        "release/*",

        # IDE/editor files
        ".vscode",
        ".idea",
        "*.swp",
        "*.swo",

        # OS files
        ".DS_Store",
        "Thumbs.db",

        # Debug and sample artifacts at repo root
        "debug_*.py",
        "*_output*.txt",
        "test_output.txt",
        "test_log.txt",
        "failures*.txt",
        "landing.png",
        "design_reference.png",

        # Agent/workflow directories
        ".agent",

        # Artifacts and temp files
        "artifacts",
        "docs/archive/*",
    ]

    # Common forbidden content (always)
    common_forbidden = [
        # Version control
        ".git",
        ".git/*",
        ".github/*",  # even in review, nested .github zips or weird packaging should fail

        # Secrets (CRITICAL)
        ".env",
        ".env.local",
        ".env.production",
        ".env.staging",

        # Obsolete infrastructure
        "copilot",
        "copilot/*",

        # Database files
        "qr.db",
        "*.db",
        "*.db-journal",
        "*.db-wal",
        "*.db-shm",

        # Python compiled files (Double check to ensure no shipping)
        "__pycache__",
        "__pycache__/*",
        "*.pyc",
        "*.pyo",
        "*.pyd",

        # Runtime-generated directories
        "print_inbox",
        "print_inbox/*",
        "private",
        "private/*",
        "instance",
        "instance/*",

        # Debug/test artifacts
        "debug_size.py",
        "debug_*.py",
        "test_output.txt",
        "*_output*.txt",
        "landing.png",
        "*.log",
        "error.txt",
        "result_security.txt",

        # Nested releases / zips
        "releases/*.zip",
        "*.zip",
    ]

    if profile == "prod":
        # Production deploy artifact: exclude tests/CI and most ops/dev directories.
        prod_extras_exclude = [
            ".github",
            ".github/*",
            "tests",
            "tests/*",
            "sample_photos",
            "ops",
            "ops/*",
            "systemd",
            "systemd/*",

            # Default-exclude scripts, but selectively include runtime/ops scripts via overrides
            "scripts",
            "scripts/*",
        ]

        # These are the scripts you actually need shipped for Phase 0 and for container startup.
        include_overrides = [
            ".env.example",
            "scripts/docker-entrypoint.sh",
            "scripts/wait_for_db.py",
            "scripts/print_worker.py",
            "scripts/install_print_worker.sh",
            "scripts/insite-worker.service",
        ]

        # In prod, tests/CI/scripts should never slip in except explicit overrides
        prod_forbidden_extras = [
            ".github",
            ".github/*",
            "tests",
            "tests/*",

            # Block scripts broadly; allow exact overrides above
            "scripts",
            "scripts/*",

            "ops",
            "ops/*",
            "systemd",
            "systemd/*",
        ]

        return (common_excludes + prod_extras_exclude, include_overrides, common_forbidden + prod_forbidden_extras)

    # review profile: include scripts/, tests/, .github/ so assistants/CI can run and validate.
    review_extras_exclude = [
        # Still keep runtime data excluded, but do NOT exclude scripts/tests/.github.
        # Nothing extra required here beyond common_excludes.
    ]

    include_overrides = [
        ".env.example",
    ]

    # In review, do not forbid scripts/tests/.github (we want them inside the bundle).
    # Still forbid secrets/db/runtime data via common_forbidden.
    review_forbidden = list(common_forbidden)
    # Remove the ".github/*" blanket ban for review packaging.
    # (We still exclude raw ".git" and ".env*" via common lists.)
    review_forbidden = [p for p in review_forbidden if p not in (".github/*",)]

    return (common_excludes + review_extras_exclude, include_overrides, review_forbidden)


def should_exclude(path: str, exclude_patterns, include_overrides, is_dir: bool = False) -> bool:
    """
    Check if a path should be excluded from the release.

    Args:
        path: Relative path from project root (forward slashes)
        exclude_patterns: list of glob patterns to exclude
        include_overrides: list of exact paths to force-include
        is_dir: Whether this is a directory
    """
    path = path.replace("\\", "/")
    basename = os.path.basename(path)

    # Exact include overrides win
    for override in include_overrides:
        if path == override or basename == override:
            return False

    # For directories: if any override lives under this directory, do not exclude it
    if is_dir:
        for override in include_overrides:
            if override.startswith(path.rstrip("/") + "/"):
                return False

    for pattern in exclude_patterns:
        # Full path matches
        if fnmatch.fnmatch(path, pattern):
            return True
        if fnmatch.fnmatch(path, f"*/{pattern}"):
            return True
        if fnmatch.fnmatch(path, f"{pattern}/*"):
            return True

        # Basename matches
        if fnmatch.fnmatch(basename, pattern):
            return True

        # Prefix directory exclusion
        if path.startswith(pattern.rstrip("/") + "/"):
            return True

    return False


def build_release_zip(project_root: str = None, output_dir: str = None, profile: str = "prod") -> str:
    if project_root is None:
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    if output_dir is None:
        output_dir = os.path.join(project_root, "releases")

    exclude_patterns, include_overrides, forbidden_patterns = get_profile_config(profile)

    os.makedirs(output_dir, exist_ok=True)

    # Regression Guard 1: If Dockerfile uses docker-entrypoint, ensure wait_for_db exists on disk
    dockerfile_path = os.path.join(project_root, "Dockerfile")
    if os.path.exists(dockerfile_path):
        with open(dockerfile_path, "r", encoding="utf-8") as f:
            content = f.read()
            uses_entrypoint = 'ENTRYPOINT ["/app/scripts/docker-entrypoint.sh"]' in content
            if uses_entrypoint:
                entrypoint_src = os.path.join(project_root, "scripts", "docker-entrypoint.sh")
                wait_src = os.path.join(project_root, "scripts", "wait_for_db.py")
                if not os.path.exists(entrypoint_src):
                    print("[FAIL] BUILD FAILED: Dockerfile uses scripts/docker-entrypoint.sh but file is missing.")
                    raise SystemExit(1)
                if not os.path.exists(wait_src):
                    print("[FAIL] BUILD FAILED: Dockerfile uses docker-entrypoint.sh which calls wait_for_db.py, but scripts/wait_for_db.py is missing.")
                    raise SystemExit(1)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_filename = f"insite_signs_release_{profile}_{timestamp}.zip"
    zip_path = os.path.join(output_dir, zip_filename)
    latest_path = os.path.join(output_dir, f"insite_signs_release_{profile}.zip")

    included_files = []
    excluded_files = []

    print(f"Building release from: {project_root}")
    print(f"Profile: {profile}")
    print(f"Output:  {zip_path}")
    print("-" * 60)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(project_root):
            rel_root = os.path.relpath(root, project_root)
            if rel_root == ".":
                rel_root = ""

            # Filter dirs in-place (but allow traversal into parents of included overrides)
            i = 0
            while i < len(dirs):
                d = dirs[i]
                rel_dir_path = os.path.join(rel_root, d).replace("\\", "/") if rel_root else d
                if should_exclude(rel_dir_path, exclude_patterns, include_overrides, is_dir=True):
                    del dirs[i]
                    excluded_files.append(rel_dir_path)
                else:
                    i += 1

            for filename in files:
                rel_path = os.path.join(rel_root, filename).replace("\\", "/") if rel_root else filename

                if should_exclude(rel_path, exclude_patterns, include_overrides, is_dir=False):
                    excluded_files.append(rel_path)
                    continue

                abs_path = os.path.join(root, filename)
                zf.write(abs_path, rel_path)
                included_files.append(rel_path)

    # Overwrite "latest"
    if os.path.exists(latest_path):
        os.remove(latest_path)
    shutil.copy2(zip_path, latest_path)

    # Verification summary
    print(f"\nIncluded: {len(included_files)} files")
    print(f"Excluded: {len(excluded_files)} files")
    print("-" * 60)

    # Regression Guard 2: If docker-entrypoint is included, ensure wait_for_db.py is included too
    docker_entry_included = "scripts/docker-entrypoint.sh" in included_files
    if docker_entry_included and "scripts/wait_for_db.py" not in included_files:
        print("[FAIL] BUILD FAILED: scripts/docker-entrypoint.sh is included but scripts/wait_for_db.py is NOT included.")
        os.remove(zip_path)
        if os.path.exists(latest_path):
            os.remove(latest_path)
        raise SystemExit(1)

    # Fail hard on __pycache__ (this should never be shipped in any profile)
    pycache_included = [f for f in included_files if "__pycache__" in f]
    if pycache_included:
        print("[FAIL] BUILD FAILED: __pycache__ content included (this indicates broken excludes or bad paths).")
        for f in pycache_included[:20]:
            print(f"  - {f}")
        os.remove(zip_path)
        if os.path.exists(latest_path):
            os.remove(latest_path)
        raise SystemExit(1)

    # Forbidden file check (last line of defense)
    print("\nForbidden file check:")
    forbidden_found = []
    with zipfile.ZipFile(zip_path, "r") as zf:
        for name in zf.namelist():
            # Allow explicit overrides in prod
            if name in include_overrides:
                continue
            for pattern in forbidden_patterns:
                if name == pattern or fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(name, f"*/{pattern}"):
                    forbidden_found.append((name, pattern))

    if forbidden_found:
        print("\n" + "=" * 60)
        print("[FAIL] BUILD FAILED: Forbidden files found in release!")
        print("=" * 60)
        for file_path, matched_pattern in forbidden_found:
            print(f"  - {file_path} (matched: {matched_pattern})")
        print("\nFix: remove from source, exclude it, or adjust profile rules.")
        print("=" * 60)
        os.remove(zip_path)
        if os.path.exists(latest_path):
            os.remove(latest_path)
        raise SystemExit(1)

    print("  [OK] No forbidden files found")
    print("-" * 60)
    print(f"\nRelease created: {zip_path}")
    print(f"Latest copy:     {latest_path}")

    return zip_path


def main():
    parser = argparse.ArgumentParser(description="Build a clean release zip.")
    parser.add_argument("--profile", choices=["prod", "review"], default="prod", help="Build profile.")
    parser.add_argument("--project-root", default=None, help="Project root (defaults to repo root).")
    parser.add_argument("--output-dir", default=None, help="Output directory (defaults to releases/).")
    args = parser.parse_args()

    build_release_zip(project_root=args.project_root, output_dir=args.output_dir, profile=args.profile)


if __name__ == "__main__":
    main()
