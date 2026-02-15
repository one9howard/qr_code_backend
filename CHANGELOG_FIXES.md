# CHANGELOG_FIXES

## 2026-02-15 SmartSign Layout Catalog Unification

- `services/print_catalog.py`
  - Introduced a canonical `SMARTSIGN_LAYOUT_CATALOG` object derived from `SMARTSIGN_LAYOUT_IDS`.
  - Added `is_valid_smartsign_layout()` and made `get_smartsign_layout_options()` read from catalog values.
  - `validate_layout('smart_sign', ...)` now validates against the canonical catalog (single source).
  - Why: remove layout drift between ordering, UI options, and downstream rendering.

- `routes/smart_signs.py`
  - Switched order POST layout validation to use `services.print_catalog.validate_layout(...)` and `SMART_SIGN_LAYOUTS`.
  - Why: order create path now uses the same canonical validator as catalog consumers.

- `services/pdf_smartsign.py`
  - Removed local hardcoded `valid_layouts` list.
  - Added canonical layout validation via `services.print_catalog.validate_layout(...)`.
  - PDF generator now **raises** on unknown layout IDs instead of silently falling back to `smart_v1_minimal`.
  - Dispatch now uses explicit layout->drawer mapping with hard failure on missing renderer.
  - Why: PDF rendering now enforces the same contract as order POST.

- `tests/test_smoke.py`
  - Added regression test: unknown SmartSign layout IDs are rejected by `generate_smartsign_pdf`.
  - Why: prevents future reintroduction of silent fallback drift.

## 2026-02-15 Release-Hardening Pass (Contract, Privacy, Layout, Runtime)

- `services/specs.py`
- `SPECS.md`
- `services/print_catalog.py`
  - Aligned SmartSign contract to include all implemented layouts:
    - `smart_v2_modern_split`
    - `smart_v2_elegant_serif`
    - `smart_v2_bold_frame`
  - Why: remove spec drift between contract, renderer, and print validation.

- `routes/leads.py`
  - Removed raw IP values from honeypot and rate-limit warning logs.
  - Why: avoid PII leakage in logs while preserving existing rate-limit behavior.

- `services/cleanup.py`
  - Removed property address from cleanup logs; log property ID only.
  - Why: avoid leaking sensitive listing details to logs.

- `utils/pdf_generator.py`
  - Updated modern-round portrait QR sizing to be ring-footprint aware (`1.15x` outer ring factor).
  - Added `ring_dia_pt` to `DEBUG_LAYOUT=1` diagnostics.
  - Why: prevent ring/CTA crowding by sizing QR based on true rendered footprint.

- `utils/listing_designs.py`
  - Switched fallback URL source from `BASE_URL` to `PUBLIC_BASE_URL`.
  - Hardened `_resolve_qr_url` fallback to accept only canonical QR tokens (regex-validated), refusing storage-key/path style inputs.
  - Why: prevent unsafe URL derivation and align URL generation with public routing config.

- `services/async_jobs.py`
  - Removed contradictory `failed` status path and dead duplicate SQL in `mark_failed`.
  - Standardized retry flow:
    - retryable failures -> `queued` with exponential backoff
    - terminal failures -> `dead`
  - Simplified `claim_batch` to claim `queued` and stale `processing` jobs only.
  - Why: make async status transitions deterministic and maintainable.

- `scripts/railway_start.sh`
  - Standardized web startup path through `scripts/docker-entrypoint.sh` and matching Gunicorn flags.
  - Why: remove conflicting boot behavior and avoid migration/startup drift across environments.

## 2026-02-15 Teams Property Workspace Collaboration (Broker Teams)

- `migrations/versions/044_teams_property_workspace_collaboration.py`
  - Added collaboration schema: `teams`, `team_members`, `team_invites`, `property_comments`, `property_files`, `audit_events`.
  - Added `properties.team_id` (nullable) with FK/index for team scoping.
  - Added role/status/kind constraints and retention/cleanup-related indexes.
  - Why: introduce team workspaces with role-based collaboration and file retention.

- `services/teams_collab.py`
  - Added core team workflows: create team, role enforcement, invites, invite acceptance, retention updates, team/member/invite listing.
  - Added audit event writer with request metadata capture (IP/UA when available) and minimal metadata payloads.
  - Added owner/invitee auto-assignment of unassigned properties (via agent ownership) when joining a team.
  - Why: centralize permission + membership + retention logic and keep routes thin.

- `services/team_files.py`
  - Added property workspace file lifecycle:
    - list files
    - upload files (`upload` kind) with extension allowlist
    - generate leads CSV export (`export` kind) with CSV formula-injection mitigation
    - role-aware download control (viewer export-only)
    - admin delete
    - retention cleanup for expired files.
  - Added audit events for upload/download/delete/export/cleanup actions.
  - Why: enforce role rules and retention in one service surface.

- `routes/teams.py`
  - Added `/teams` blueprint with endpoints for:
    - team list/create
    - invite acceptance
    - dashboard + property workspace
    - comments
    - file upload/export/download/delete
    - admin settings (retention + invites).
  - Enforced role gates:
    - viewer: read-only + export download only
    - member: comments/uploads/exports/download-all
    - admin: settings + file delete.
  - Why: deliver end-user Team → Property Workspace flow.

- `templates/teams/index.html`
- `templates/teams/team_dashboard.html`
- `templates/teams/property_workspace.html`
- `templates/teams/settings.html`
  - Added minimal functional UI for team creation, workspace navigation, comments/files panels, and admin settings/invites.
  - Why: provide usable collaboration UX with existing style patterns.

- `app.py`
  - Registered `teams_bp`.
  - Why: activate new team routes.

- `templates/landing.html`
  - Updated Teams header link: authenticated users go to `/teams`, unauthenticated users keep sales `mailto`.
  - Why: make team workspace reachable from landing while preserving sales CTA for guests.

- `templates/base.html`
  - Added Teams link to authenticated drawer menu.
  - Why: make workspace reachable from app navigation.

- `scripts/cleanup_team_files.py`
  - Added CLI cleanup entrypoint with `--dry-run`.
  - Why: support cron/manual deletion of expired team attachments.

- `tests/factories.py`
  - Added `TeamFactory`, `create_team`, `add_member` helpers.
  - Why: deterministic team setup in tests.

- `tests/test_teams_collaboration.py`
  - Added deterministic coverage for:
    - team creation + owner membership + property auto-assignment
    - viewer/member/admin permission boundaries
    - invite acceptance constraints
    - retention updates
    - expired file cleanup behavior.
  - Why: prevent regressions in role rules and retention lifecycle.

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
