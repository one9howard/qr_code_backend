# CHANGELOG_FIXES

## 2026-02-15 Test Suite Consolidation (Low-Value/Redundant Trim)

- `tests/test_events_csrf_runtime.py` (deleted)
  - Removed duplicate runtime/code-inspection coverage already present in `tests/test_events_csrf_exempt.py`.
  - Why: redundant assertions for the same CSRF exemption behavior.

- `tests/test_import.py` (deleted)
- `tests/test_repro_500.py` (deleted)
- `tests/test_placeholder.py` (deleted)
  - Removed import-only/placeholder/repro overlap tests.
  - Why: low-signal checks duplicated by stronger integration tests (`test_property_creation_flow.py`, existing route/service tests).

- `tests/test_guest_security.py` (deleted)
  - Removed weak/placeholder security checks (`status != 403`, placeholder `pass`) that were not producing actionable failures.
  - Why: coverage already represented by stronger guest/linking and auth tests.

- `tests/test_listing_kits_imports.py`
  - Replaced `assert True` import smoke with callable entrypoint checks (`start_kit`, `download_kit`, `generate_kit`).
  - Why: keeps import/entrypoint protection while making failures actionable.

- `tests/test_agent_claiming_security.py`
  - Removed duplicated hijack test overlapping with `tests/test_agent_identity_integrity.py` claim-conflict coverage.
  - Why: avoid duplicate setup and assertions for same security rule.

- `tests/test_printing_atomic.py`
  - Removed duplicate PDF download test already covered in `tests/test_print_jobs.py`.
  - Why: keep endpoint behavior coverage without duplicating essentially identical assertions.

- `tests/test_onboarding_activation.py`
  - Removed low-signal dashboard presence tests and a placeholder `pass` test.
  - Why: retained scenario tests with concrete behavior assertions (active dashboard, first scan banner, first lead rendering).

- `tests/test_strategy_alignment.py`
  - Removed placeholder and source-inspection-only tests.
  - Why: prefer runtime behavior tests over brittle source-string checks.

- `tests/test_pro_features.py` (rewritten)
  - Replaced broad `unittest` assertions with 3 focused pytest checks:
    - free lead limit constant
    - CSV export auth gate
    - analytics rollup for unknown user
  - Why: tighter, deterministic assertions with clearer failure modes.

## 2026-02-14 Agent Identity + Output Integrity Patch

- `migrations/versions/043_enforce_unique_agent_email_ci.py`
  - Added a case-insensitive uniqueness guard for `agents.email` via `UNIQUE INDEX uq_agents_email_ci ON lower(email)`.
  - Canonicalizes existing emails with `lower(trim(email))`.
  - Detects duplicates before adding the index and fails with a clear admin remediation SQL snippet (no silent data deletion).

- `utils/agent_identity.py`
  - Added shared agent identity helpers:
    - email normalization (`strip + lower`)
    - deterministic lookup by normalized email
    - explicit verified-claim flow that prevents cross-user reassignment.

- `routes/auth.py`
  - Registration now uses normalized, case-insensitive email checks.
  - Replaced blind `INSERT INTO agents` with deterministic lookup/create/update logic.
  - Prevents duplicate/hostile reassignment when an agent row is already claimed by a different user.
  - Verify/login claim behavior now routes through shared verified claim helper.

- `routes/agent.py`
  - Submit flow now resolves agent identity deterministically by normalized email.
  - Blocks reassignment if email is already claimed by another user.
  - Preserves unclaimed records without creating duplicate agent rows.
  - Replaced silent upload failure with explicit `logger.exception(...)`.

- `routes/account.py`
  - Replaced implicit direct linking with explicit verified claim helper.
  - Avoids creating claimed duplicates when agent identity already exists.

- `routes/dashboard.py`
  - Property creation path now uses explicit claim behavior and normalized identity lookup to avoid duplicate agent rows.

- `services/printing/layout_utils.py`
- `services/fulfillment.py`
- `services/pdf_smartsign.py`
- `utils/pdf_generator.py`
  - Removed/limited output-integrity `except: pass` patterns in rendering/fulfillment paths.
  - Added explicit logging (`warning/exception`) and raising behavior where broken output must fail fast.

- `tests/test_agent_identity_integrity.py`
  - Added regression coverage for:
    - no duplicate agent row after registration
    - no duplicate agent row after submit with same email
    - cross-user claim conflict is rejected
    - case-insensitive email maps to a single agent identity.

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
