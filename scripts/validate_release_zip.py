#!/usr/bin/env python3
"""Validate a release ZIP artifact.

Workflow:
- Someone sends you a zip (or you find one in releases/)
- You want a single red/green verdict with strict checks

Usage:
  python scripts/validate_release_zip.py path/to/insite_signs_release_*.zip

Options:
  --skip-import    Skip the import smoke (useful if deps aren't installed in this Python env)

Exit code:
  0 = ok
  1 = failed
"""

import os
import sys
import zipfile
import tempfile
import subprocess
import argparse


def fail(msg: str) -> None:
    print(f"[FAIL] {msg}")
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a release ZIP artifact")
    parser.add_argument("zip_path", help="Path to the zip")
    parser.add_argument(
        "--skip-import",
        action="store_true",
        help="Skip import smoke (useful if deps are not installed in this Python env)",
    )
    args = parser.parse_args()

    zip_path = os.path.abspath(args.zip_path)
    if not os.path.isfile(zip_path):
        fail(f"Zip not found: {zip_path}")

    here = os.path.abspath(os.path.dirname(__file__))
    check_script = os.path.join(here, "check_release_clean.py")
    if not os.path.isfile(check_script):
        fail("Missing scripts/check_release_clean.py")

    with tempfile.TemporaryDirectory() as td:
        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONPYCACHEPREFIX"] = td

        print(f"[INFO] Extracting: {zip_path}")
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(td)
        except Exception as e:
            fail(f"Could not extract zip: {e}")

        # 1) Release cleanliness
        print("[CHECK] Release cleanliness...")
        try:
            subprocess.check_call([sys.executable, check_script, "--root", td], env=env)
        except subprocess.CalledProcessError:
            fail("Release cleanliness check failed")

        # 2) Minimal operational files check
        print("[CHECK] Required operational files...")
        required_files = ["app.py", "migrate.py", "alembic.ini", "extensions.py"]
        missing = [f for f in required_files if not os.path.isfile(os.path.join(td, f))]
        if not (
            os.path.isfile(os.path.join(td, "Procfile"))
            or os.path.isfile(os.path.join(td, "gunicorn.conf.py"))
        ):
            missing.append("Procfile or gunicorn.conf.py")
        if missing:
            fail("Missing required files: " + ", ".join(missing))

        # 3) Syntax check (no bytecode)
        print("[CHECK] Python syntax (ast.parse)...")
        check_syntax_script = (
            "import ast, os, sys\n"
            "errors = 0\n"
            "for r, d, f in os.walk('.'): \n"
            "  if any(s in r for s in ['.git', '.venv', 'venv', 'node_modules', '__pycache__']):\n"
            "    continue\n"
            "  for file in f:\n"
            "    if file.endswith('.py'):\n"
            "      p = os.path.join(r, file)\n"
            "      try:\n"
            "        with open(p, 'rb') as fh: ast.parse(fh.read())\n"
            "      except Exception as e:\n"
            "        print(f'[FAIL] Syntax error: {p}: {e}')\n"
            "        errors += 1\n"
            "if errors: sys.exit(1)\n"
        )
        try:
            subprocess.check_call([sys.executable, "-c", check_syntax_script], cwd=td, env=env)
        except subprocess.CalledProcessError:
            fail("Syntax check failed")

        # 4) Import check (cheap smoke)
        if not args.skip_import:
            print("[CHECK] Import smoke (app + extensions)...")
            smoke = (
                "import os\n"
                "os.environ.setdefault('DATABASE_URL','postgresql://mock:mock@localhost/mock')\n"
                "os.environ.setdefault('SECRET_KEY','mock-secret')\n"
                "os.environ.setdefault('FLASK_ENV','production')\n"
                "os.environ.setdefault('PUBLIC_BASE_URL','https://example.com')\n"
                "os.environ.setdefault('STRIPE_SECRET_KEY','sk_live_mock')\n"
                "os.environ.setdefault('PRINT_JOBS_TOKEN','mock-print-token')\n"
                "import app, extensions\n"
                "print('OK')\n"
            )
            try:
                subprocess.check_call([sys.executable, "-c", smoke], cwd=td, env=env)
            except subprocess.CalledProcessError:
                fail("Import smoke failed")

    print("[SUCCESS] Release zip validated.")


if __name__ == "__main__":
    main()
