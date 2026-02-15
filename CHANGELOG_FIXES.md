# CHANGELOG_FIXES

- `RELEASE_MANIFEST.json`
  - Added explicit release allowlist (`files`, `dirs`, `exclude_paths`, `optional_top_level`) used as source-of-truth for packaging/validation.

- `scripts/build_release_zip.py`
  - Enforced allowlist-only staging from `RELEASE_MANIFEST.json`.
  - Added hard failure on missing allowlisted paths.
  - Added guardrail to fail if anything outside the allowlist is copied to staging.
  - Preserved generated `RELEASE_MANIFEST.json` in artifact with allowlist metadata + file hashes.

- `scripts/validate_release_zip.py`
  - Added strict allowlist validation for extracted artifacts.
  - Fails if top-level extras appear beyond allowlist.
  - Fails if allowlisted entries are missing.
  - Added runtime pin consistency check (`Dockerfile`, `runtime.txt`, `.python-version`).
  - Enforced required `SPECS.md` presence and SPECS sync validation.

- `scripts/check_release_clean.py`
  - Added explicit root-level bans for debug helpers:
    - `get_code.py`
    - `get_docker_logs.py`
    - `test_manual_import*.py`
    - `*manual_import*` at repo root.

- `scripts/devtools/get_code.py`
- `scripts/devtools/get_docker_logs.py`
- `scripts/devtools/test_manual_import.py`
- `scripts/devtools/test_manual_import_v2.py`
  - Relocated root debug helper scripts into `scripts/devtools/`.

- `migrations/env.py`
  - Fixed env handling so Postgres scheme enforcement runs only when `DATABASE_URL` is provided.
  - Added fallback to `alembic.ini` URL when `DATABASE_URL` is unset.
  - Added clear error when both env + ini URL are missing.
  - Added credential redaction in error paths.

- `database.py`
  - Restricted SQL statement logging to non-secure environments only:
    - log SQL only when not production and not staging.

- `app.py`
  - Enabled `ProxyFix` in staging and production when `TRUST_PROXY_HEADERS=true`.

- `requirements-test.in`
- `requirements-test.txt`
- `Dockerfile`
  - Removed Playwright test dependency and browser install path (unused in test suite).
  - Kept Python runtime aligned to 3.14.3.

- `scripts/release_gate.py`
  - Stabilized gate behavior by avoiding false failures on transient local bytecode artifacts while still enforcing real forbidden files.
  - Kept acceptance runner invocation canonical (`scripts/release_acceptance.sh`).

- `tests/test_qr_logo_rendering.py`
  - Removed module-level skip pattern; tests run with real imports.

- `tests/test_yard_sign_pdf.py`
  - Removed exception-swallow behavior and replaced with explicit assertions.

- `tests/test_dashboard_smartsigns_phase1.py`
  - Removed `try/except TypeError` suppression in activation test.

- `tests/test_fix_cleanup.py`
  - Replaced exception-swallowing test logic with explicit mocks/assertions.
  - Removed no-op placeholder test.

- `tests/test_agent_claiming_security.py`
  - Replaced pass-only branch with explicit response-status assertion for clearer failure reporting.
