import os
import sys
import argparse


def check_release_clean(root: str) -> None:
    """Fail if artifacts exist in a would-be release tree."""
    root = os.path.abspath(root)

    # Allowed PDF locations (fixtures only)
    allowed_pdf_dirs = [
        os.path.join(root, "tests", "fixtures"),
        os.path.join(root, "tests", "data"),
    ]

    errors = []

    # Banned extensions and patterns
    banned_extensions = [
        ".log",
        ".sqlite",
        ".DS_Store",
        ".pyc",
        ".pyo",
        ".pyi",
        ".dump",
    ]
    banned_patterns = ["dump.sql", "dump.wkr"]
    banned_prefixes = ["debug_"]
    banned_dir_names = [
        "__pycache__",
        "instance",
        "tmp",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
    ]

    for dirpath, dirnames, filenames in os.walk(root):
        # Exclude common dev/system dirs completely from traversal
        for skip_dir in [".git", ".venv", "venv", "node_modules"]:
            if skip_dir in dirnames:
                dirnames.remove(skip_dir)

        # 1) Check for banned directories by name
        rel_path = os.path.relpath(dirpath, root)
        parts = rel_path.split(os.sep)

        for part in parts:
            if part in banned_dir_names:
                # Ignore .gitignore files in these directories
                artifacts = [f for f in filenames if f != ".gitignore"]
                if artifacts:
                    errors.append(f"Forbidden directory '{part}' contains artifacts: {dirpath}")
                break

        # 2) Check filenames for banned patterns
        for f in filenames:
            path = os.path.join(dirpath, f)

            # PDFs only allowed in tests fixtures/data
            if f.endswith(".pdf"):
                is_allowed = any(os.path.commonpath([path, allowed]) == allowed for allowed in allowed_pdf_dirs)
                if not is_allowed:
                    errors.append(f"Found PDF artifact: {path}")

            # Banned extensions
            for ext in banned_extensions:
                if f.endswith(ext):
                    errors.append(f"Found banned file ({ext}): {path}")

            # Banned exact filenames
            if f in banned_patterns:
                errors.append(f"Found banned file (pattern): {path}")

            # Banned prefixes
            for prefix in banned_prefixes:
                if f.startswith(prefix):
                    errors.append(f"Found debug artifact: {path}")

    if errors:
        print("Release Check FAILED:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)

    print("Release Check PASSED.")
    sys.exit(0)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fail if release artifacts exist")
    parser.add_argument("--root", default=".", help="Root directory to scan")
    args = parser.parse_args()
    check_release_clean(args.root)


if __name__ == "__main__":
    main()
