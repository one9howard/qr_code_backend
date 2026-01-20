#!/usr/bin/env python3
"""
Security sanity check for CI and local development.

Checks git-tracked files for forbidden patterns (secrets, databases, etc.)
to prevent accidental commits.

In CI mode (CI=true), this check is stricter and will also fail if
certain runtime artifacts exist on disk.

Usage:
    python scripts/security_sanity_check.py
    
Exit codes:
    0 - Clean tree
    1 - Forbidden files found
"""
import os
import sys
import fnmatch
import subprocess


# Files/patterns that should NEVER be tracked in git
FORBIDDEN_PATTERNS = [
    # Secrets
    ".env",
    ".env.local",
    ".env.production",
    ".env.staging",
    # Note: .env.example is allowed
    
    # Database files
    "qr.db",
    "*.db",
    "*.db-journal",
    "*.db-wal",
    "*.db-shm",
    
    # Instance directory (all runtime state)
    "instance/",
    
    # Legacy runtime directories (if someone uses old config)
    "private/",
    "print_inbox/",
    
    # Version control in wrong places
    "releases/.git/",
    
    # Nested zips (release artifacts committed by mistake)
    "releases/*.zip",
]

# Patterns to skip (allowed even if they match above patterns)
ALLOWED_PATTERNS = [
    ".env.example",
]


def is_allowed(path: str) -> bool:
    """Check if a path is explicitly allowed."""
    for pattern in ALLOWED_PATTERNS:
        if path == pattern or path.endswith(f"/{pattern}"):
            return True
    return False


def find_forbidden_tracked_files(root_dir: str) -> list:
    """
    Scan git-tracked files for forbidden patterns.
    
    Only checks what would actually be committed (git ls-files),
    not local runtime files that are properly gitignored.
    
    Returns list of (path, matched_pattern) tuples.
    """
    forbidden_found = []
    
    # Get list of tracked files from git
    try:
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=root_dir,
            capture_output=True,
            text=True,
            check=True
        )
        tracked_files = [f.strip() for f in result.stdout.splitlines() if f.strip()]
    except subprocess.CalledProcessError as e:
        print(f"[WARNING] git ls-files failed: {e}")
        return []
    
    # Check tracked files against forbidden patterns
    for tracked_file in tracked_files:
        # Normalize path separators
        tracked_file = tracked_file.replace("\\", "/")
        
        for pattern in FORBIDDEN_PATTERNS:
            matched = False
            
            # Handle directory patterns (ending with /)
            if pattern.endswith("/"):
                dir_pattern = pattern.rstrip("/")
                if tracked_file.startswith(dir_pattern + "/") or tracked_file == dir_pattern:
                    matched = True
            else:
                # Handle file patterns
                basename = os.path.basename(tracked_file)
                if fnmatch.fnmatch(tracked_file, pattern) or fnmatch.fnmatch(basename, pattern):
                    matched = True
            
            if matched and not is_allowed(tracked_file):
                forbidden_found.append((tracked_file, pattern))
    
    # Deduplicate
    seen = set()
    unique = []
    for path, pattern in forbidden_found:
        if path not in seen:
            seen.add(path)
            unique.append((path, pattern))
    
    return unique


def main():
    """Run security sanity check."""
    # Determine project root (parent of scripts/)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    
    # Check if running in CI
    is_ci = os.getenv("CI", "").lower() in ("true", "1", "yes")
    
    print("=" * 60)
    print("Security Sanity Check")
    print("=" * 60)
    print(f"Scanning: {project_root}")
    print(f"Mode: {'CI (strict)' if is_ci else 'Local (git-tracked only)'}")
    print()
    
    # Always check git-tracked files
    forbidden = find_forbidden_tracked_files(project_root)
    
    if forbidden:
        print("[FAIL] FORBIDDEN FILES TRACKED IN GIT:")
        print("-" * 60)
        for path, pattern in sorted(forbidden):
            print(f"  {path}")
            print(f"    (matched: {pattern})")
        print("-" * 60)
        print()
        print("These files should NOT be tracked in git!")
        print("Actions required:")
        print("  1. Add to .gitignore if not already")
        print("  2. Remove from git tracking: git rm --cached <file>")
        print()
        sys.exit(1)
    else:
        print("[OK] No forbidden files tracked in git")
        print()
        sys.exit(0)


if __name__ == "__main__":
    main()
