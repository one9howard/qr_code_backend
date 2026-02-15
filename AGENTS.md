# Codex Agent Instructions (InSite Signs)

These instructions are authoritative for automated changes in this repo. Follow them exactly.

## Ground rules
- Do **not** assume anything. Confirm by reading the current files and running commands.
- Keep changes **minimal and surgical**. No refactors unless required to fix a failing check.
- Never log or print secrets. Treat **staging like production** for privacy and logging.

## Canonical commands (use these first)
### Validation
- Run the release validator before and after changes:
  - `python scripts/validate_release_zip.py --skip-import` (or repo-equivalent if args differ)

### Tests (canonical)
- Preferred: `bash scripts/run_tests_in_docker.sh`
- Direct: `docker compose run --rm web pytest -q -ra`

### Local grep checks (must stay clean)
- Skips:
  - `rg -n "skip\\(|@pytest\\.mark\\.skip|allow_module_level=True" tests || true`
- Secrets / credentials:
  - `rg -n "DATABASE_URL|postgresql://|sk_live|sk_test|MAILJET_|SMTP_PASS|SECRET_KEY" .`

## Definition of Done (DoD)
A change is only acceptable if ALL are true:
1) `scripts/validate_release_zip.py` passes.
2) `bash scripts/run_tests_in_docker.sh` passes.
3) `pytest -q -ra` shows **0 skipped** in the default suite.
   - If a test is truly optional (OS/dep-specific), it must be:
     - marked explicitly (e.g., `@pytest.mark.optional`), AND
     - excluded from default runs (so default suite is 0 skipped), AND
     - documented in this file.

## Release artifacts policy
- The “release gate” must be runnable from a clean checkout.
- `SPECS.md` must exist (or be generated deterministically during packaging) and validation must fail if it’s missing.
- Python version pins must be consistent across:
  - `Dockerfile` base image
  - `runtime.txt`
  - `.python-version`
- Standard is **Python 3.14.x** (prefer pinned patch, e.g., 3.14.3, unless policy is changed explicitly).

## Docker policy
- Use `docker compose run --rm` for one-off commands to avoid container pile-up.
- Gunicorn start must bind to `0.0.0.0:${PORT}` with a local fallback `${PORT:-8080}`.
- Avoid login shells (`sh -lc`) unless required; prefer `sh -c`.
- Entrypoints must end with `exec "$@"` so signals are handled correctly.

## Logging and PII policy (strict)
- Never print raw `DATABASE_URL` or any credential-bearing URL.
- Implement and use a redaction helper wherever a URL might appear in logs/exceptions.
- Do not log buyer email, phone, or other direct identifiers. Use IDs.
- Do not enable raw SQL logging in staging.

## Testing policy (no “fake green”)
- Tests must create their own data. Never `pytest.skip()` due to “missing DB rows.”
- If database isolation truncates tables per test, fixtures must insert required rows for each test.
- Module-level skips (`allow_module_level=True`) are not allowed in default suite.

## Print/layout policy
- CTA text belongs in the **bottom identity band**, not under the QR.
- QR sizing must be computed from available area (excluding identity band and margins) and must not be artificially capped in a way that prevents “scan from car/street.”
- If adding layout debug, gate it behind `DEBUG_LAYOUT=1` and keep logs free of PII.

## Output requirements for any task
When finishing work, provide:
- A concise `CHANGELOG_FIXES.md` listing:
  - what changed
  - why it changed
  - file paths touched
- Evidence snippets from:
  - validator output
  - docker test runner output
  - pytest `-ra` summary (showing 0 skipped)
  - grep checks for secrets/PII leakage