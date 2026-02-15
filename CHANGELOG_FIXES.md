# CHANGELOG_FIXES

- `scripts/run_tests_in_docker.sh`
  - Kept a single `docker compose run --rm ... bash -lc 'set -euo pipefail; ...'` chain.
  - Ensured explicit phase banners and ordered steps: reset DB, migrate, fixture gate, `pytest -q -ra`.
  - Ensures non-zero exit on any failure.

- `docker-compose.yml`
  - Added `PYTHONPATH=/app` for the `web` service so direct `docker compose run --rm web pytest ...` resolves app imports reliably.

- `Dockerfile`
  - Added `PYTHONPATH=/app` at image level to keep CLI/module import behavior consistent in containers.

- `tests/test_lead_attribution.py`
  - Replaced skip-based tests with deterministic data seeding helpers.
  - Tests now create their own users/agents/properties/assets and run end-to-end without `pytest.skip(...)`.
  - Updated Flask test-client cookie API usage for current Werkzeug signature.

- `tests/test_ai_readiness.py`
  - Removed hard skip from request-correlation test so it runs in default suite.

- `tests/test_yard_sign_pdf.py`
  - Removed two hard skips.
  - Fixed outdated/invalid mocks to match current yard-sign generation behavior.
  - Updated assertions for two-page front/back rendering.

- `utils/pdf_generator.py`
  - Removed artificial QR cap in modern-round landscape sizing path.
  - QR size now uses available body area (width/height after margins).
  - Added `DEBUG_LAYOUT=1` logging for computed QR size and available area.
