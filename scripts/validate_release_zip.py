#!/usr/bin/env python3
"""Validate a release ZIP artifact."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile


def fail(msg: str) -> None:
    print(f"[FAIL] {msg}")
    sys.exit(1)


def _normalize_relpath(path: str) -> str:
    return path.replace("\\", "/").strip().strip("/")


def _is_valid_relpath(path: str) -> bool:
    if not path:
        return False
    if os.path.isabs(path):
        return False
    parts = [p for p in _normalize_relpath(path).split("/") if p]
    return not any(part in {".", ".."} for part in parts)


def _load_allowlist_from_manifest(manifest_path: str) -> dict:
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except Exception as e:
        fail(f"Could not parse RELEASE_MANIFEST.json: {e}")

    allowlist = manifest.get("allowlist")
    if not isinstance(allowlist, dict):
        fail("RELEASE_MANIFEST.json missing required 'allowlist' object.")

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
            fail(f"{field_name} must be a list of strings.")
        for v in values:
            if not _is_valid_relpath(v):
                fail(f"Invalid relative path in {field_name}: {v!r}")

    files = sorted({_normalize_relpath(p) for p in files})
    dirs = sorted({_normalize_relpath(p) for p in dirs})
    exclude_paths = sorted({_normalize_relpath(p) for p in exclude_paths})
    optional_top_level = sorted({_normalize_relpath(p) for p in optional_top_level})

    if "RELEASE_MANIFEST.json" not in files:
        files.append("RELEASE_MANIFEST.json")

    return {
        "files": files,
        "dirs": dirs,
        "exclude_paths": exclude_paths,
        "optional_top_level": optional_top_level,
    }


def _validate_allowlist_enforcement(root_dir: str, allowlist: dict) -> None:
    top_entries = sorted(
        name for name in os.listdir(root_dir) if name not in {".DS_Store"}
    )
    allowed_top = {
        _normalize_relpath(p).split("/")[0] for p in allowlist["files"] + allowlist["dirs"] + allowlist["optional_top_level"]
    }
    allowed_top.add("RELEASE_MANIFEST.json")

    extras = [name for name in top_entries if name not in allowed_top]
    if extras:
        fail("Top-level entries not allowed by RELEASE_MANIFEST allowlist: " + ", ".join(extras))

    missing = []
    for rel_file in allowlist["files"]:
        if rel_file == "RELEASE_MANIFEST.json":
            continue
        if not os.path.isfile(os.path.join(root_dir, rel_file)):
            missing.append(rel_file)
    for rel_dir in allowlist["dirs"]:
        if not os.path.isdir(os.path.join(root_dir, rel_dir)):
            missing.append(rel_dir)
    if missing:
        fail("Allowlisted entries missing from artifact: " + ", ".join(missing))


def _extract_python_version_from_docker_tag(tag: str) -> str | None:
    match = re.match(r"^(\d+\.\d+(?:\.\d+)?)(?:[.-].*)?$", tag.strip())
    return match.group(1) if match else None


def _read_docker_python_tag(dockerfile_path: str) -> str:
    with open(dockerfile_path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            match = re.match(r"^FROM\s+python:([^\s]+)", line, re.IGNORECASE)
            if match:
                return match.group(1)
    raise ValueError("Could not find `FROM python:*` in Dockerfile")


def _read_runtime_version(runtime_path: str) -> str:
    raw = open(runtime_path, "r", encoding="utf-8").read().strip()
    if raw.startswith("python-"):
        raw = raw[len("python-") :]
    if not raw:
        raise ValueError("runtime.txt is empty")
    return raw


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a release ZIP artifact")
    parser.add_argument("zip_path", help="Path to the zip")
    parser.add_argument(
        "--check-stage",
        choices=["staging", "production"],
        default=os.environ.get("RELEASE_CHECK_STAGE", "staging"),
        help="Stage to emulate during import smoke.",
    )
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

        print("[CHECK] Release cleanliness...")
        try:
            subprocess.check_call([sys.executable, check_script, "--root", td], env=env)
        except subprocess.CalledProcessError:
            fail("Release cleanliness check failed")

        print("[CHECK] Required operational files...")
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
        missing = [f for f in required_files if not os.path.isfile(os.path.join(td, f))]
        if not any(
            name.lower().startswith("readme")
            for name in os.listdir(td)
            if os.path.isfile(os.path.join(td, name))
        ):
            missing.append("README*")
        if not os.path.isdir(os.path.join(td, "tests")):
            missing.append("tests/")
        if not (
            os.path.isfile(os.path.join(td, "Procfile"))
            or os.path.isfile(os.path.join(td, "gunicorn.conf.py"))
        ):
            missing.append("Procfile or gunicorn.conf.py")
        if missing:
            fail("Missing required files: " + ", ".join(missing))

        manifest_path = os.path.join(td, "RELEASE_MANIFEST.json")
        if not os.path.isfile(manifest_path):
            fail("Missing RELEASE_MANIFEST.json")

        print("[CHECK] RELEASE_MANIFEST.json includes critical files...")
        allowlist = _load_allowlist_from_manifest(manifest_path)

        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        except Exception as e:
            fail(f"Could not parse RELEASE_MANIFEST.json: {e}")
        manifest_paths = {entry.get("path") for entry in manifest.get("files", []) if isinstance(entry, dict)}
        for required in ("SPECS.md", ".python-version", "Dockerfile", "runtime.txt"):
            if required not in manifest_paths:
                fail(f"RELEASE_MANIFEST.json missing required file entry: {required}")
        print("[CHECK] RELEASE_MANIFEST.json coverage OK.")

        print("[CHECK] Allowlist enforcement (no extras beyond manifest)...")
        _validate_allowlist_enforcement(td, allowlist)
        print("[CHECK] Allowlist enforcement passed.")

        print("[CHECK] Runtime pin consistency...")
        docker_tag = _read_docker_python_tag(os.path.join(td, "Dockerfile"))
        docker_ver = _extract_python_version_from_docker_tag(docker_tag)
        runtime_ver = _read_runtime_version(os.path.join(td, "runtime.txt"))
        py_ver = open(os.path.join(td, ".python-version"), "r", encoding="utf-8").read().strip()
        if not docker_ver:
            fail(f"Could not parse python version from Dockerfile tag: {docker_tag}")
        if docker_ver != runtime_ver or docker_ver != py_ver:
            fail(
                "Python version pins are inconsistent: "
                f"Dockerfile={docker_tag}, runtime.txt={runtime_ver}, .python-version={py_ver}"
            )
        print(
            "[Runtime] Python version pins consistent: "
            f"Dockerfile={docker_tag}, runtime.txt=python-{runtime_ver}, .python-version={py_ver}"
        )

        print("[CHECK] SPECS sync check...")
        specs_check_script = os.path.join(td, "scripts", "check_specs_sync.py")
        try:
            subprocess.check_call([sys.executable, specs_check_script], cwd=td, env=env)
        except subprocess.CalledProcessError:
            fail("SPECS sync check failed")
        print("[CHECK] SPECS sync check passed.")

        print("[CHECK] DATABASE_URL redaction self-test...")
        redaction_check = (
            "from utils.redaction import redact_database_url\n"
            "raw='postgresql://demo:supersecret@db.example:5432/insite'\n"
            "masked=redact_database_url(raw)\n"
            "assert 'supersecret' not in masked\n"
            "assert '****' in masked\n"
            "assert 'db.example' in masked\n"
            "print('[CHECK] DATABASE_URL redaction self-test passed.')\n"
        )
        try:
            subprocess.check_call([sys.executable, "-c", redaction_check], cwd=td, env=env)
        except subprocess.CalledProcessError:
            fail("DATABASE_URL redaction self-test failed")

        print("[CHECK] Python syntax (ast.parse)...")
        check_syntax_script = (
            "import ast, os, sys\n"
            "errors = 0\n"
            "for r, d, f in os.walk('.'):\n"
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

        if not args.skip_import:
            print("[CHECK] Import smoke (app + extensions)...")
            stripe_secret = "sk_live_mock" if args.check_stage == "production" else "sk_test_mock"
            stripe_publishable = "pk_live_mock" if args.check_stage == "production" else "pk_test_mock"
            smoke = (
                "import os\n"
                "os.environ.setdefault('DATABASE_URL','postgresql://mock:mock@localhost/mock')\n"
                "os.environ.setdefault('SECRET_KEY','mock-secret')\n"
                "os.environ.setdefault('FLASK_ENV','production')\n"
                f"os.environ.setdefault('APP_STAGE','{args.check_stage}')\n"
                "os.environ.setdefault('STORAGE_BACKEND','s3')\n"
                "os.environ.setdefault('S3_BUCKET','mock-bucket')\n"
                "os.environ.setdefault('PUBLIC_BASE_URL','https://example.com')\n"
                f"os.environ.setdefault('STRIPE_SECRET_KEY','{stripe_secret}')\n"
                f"os.environ.setdefault('STRIPE_PUBLISHABLE_KEY','{stripe_publishable}')\n"
                "os.environ.setdefault('SKIP_STRIPE_PRICE_WARMUP','1')\n"
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
