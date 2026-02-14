# CHANGELOG_FIXES

## P0-1 Test Runner Reliability
- Reworked `scripts/run_tests_in_docker.sh` to execute reset + migrate + fixture gate + pytest in a single `bash -lc` command with `set -euo pipefail`.
- Added phase banners:
  - `[Runner] Resetting test DB...`
  - `[Runner] Running migrations...`
  - `[Runner] Running pytest...`
- Added `scripts/check_pytest_fixtures.py` and wired it into the canonical runner to fail if `mocker` fixture is missing.

Files:
- `scripts/run_tests_in_docker.sh`
- `scripts/check_pytest_fixtures.py`
- `requirements-test.in`
- `requirements-test.txt`
- `tests/test_release_gate.py`

## P0-2 SPECS Gate and Release Packaging
- Release build now generates and sync-checks `SPECS.md` before packaging.
- Release artifact now explicitly includes `.python-version` and verifies required operational files.
- Validator now hard-fails if `SPECS.md` is missing or out of sync.
- Validator also checks `RELEASE_MANIFEST.json` contains critical files.

Files:
- `scripts/build_release_zip.py`
- `scripts/validate_release_zip.py`

## P0-3 Python Runtime Pin Consistency
- Standardized runtime pin policy to patch-level `3.14.3`.
- Docker base image pinned to `python:3.14.3-slim`.
- Added `.python-version` with `3.14.3`.
- Validator now checks consistency across Dockerfile/runtime/.python-version.

Files:
- `Dockerfile`
- `runtime.txt`
- `.python-version`
- `requirements.txt`
- `scripts/validate_release_zip.py`
- `scripts/build_release_zip.py`

## P0-4 DATABASE_URL Redaction Safety
- Added shared URL redaction helper for safe DSN logging.
- Replaced risky DB URL logging paths with redacted output.
- Added redaction self-test in release validator.
- Fixed script import-path handling so DB helper scripts can import redaction in container entrypoint context.

Files:
- `utils/redaction.py`
- `database.py`
- `migrate.py`
- `scripts/wait_for_db.py`
- `scripts/check_schema_ready.py`
- `scripts/validate_release_zip.py`

## P1-1 Modern Round / Yard QR Size Behavior
- Removed artificial cap behavior from modern-round portrait QR sizing.
- QR size now derives from available body area (excluding bottom identity band) with explicit layout debug logging.
- Added DEBUG-layout logs for landscape split path used by yard layouts.

Files:
- `utils/pdf_generator.py`

## P1-2 Release Hygiene
- Removed tracked Docker log dumps containing LAN/local-path noise.
- Added ignore rules to prevent reintroducing those files.
- Made compose `.env` optional in release/dev usage.

Files:
- `docker_logs.txt` (removed)
- `last_docker_logs.txt` (removed)
- `.gitignore`
- `docker-compose.yml`

## Additional Requested Hardening
- Auth flow now handles verification email failure explicitly:
  - staging/prod: registration/resend blocks and rolls back on delivery failure.
  - dev/test: controlled debug code path displays verification code.
- Added regression tests for the above auth behavior.
- Added release-smoke env toggle for offline validation without Stripe network calls while preserving production-like `FLASK_ENV` + `APP_STAGE`.
- Replaced remaining `datetime.utcnow()` usage with timezone-aware UTC.

Files:
- `routes/auth.py`
- `tests/test_auth_verification_delivery.py`
- `app.py`
- `utils/logger.py`
- `scripts/reconcile_stuck_orders.py`
- `scripts/build_release_zip.py`
- `scripts/validate_release_zip.py`
