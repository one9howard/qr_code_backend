# InSite Signs - Operations Runbook

## 1. Development Environment

### Requirements
*   Docker & Docker Compose
*   Python 3.10+
*   PostgreSQL 14+

### Quick Start
```bash
# Start Infrastructure (DB, Worker, Web)
docker compose up -d --build

# Run Migrations
docker compose run --rm web python migrate.py

# Tail Logs
docker compose logs -f
```

### Testing
```bash
# Run Unit/Integration Tests
pytest

# Verify Release Build
python scripts/check_release_clean.py
```

## 2. Production Deployment (Railway/Cloud)

### Services
The application requires **TWO** distinct services sharing the same repo/image:

1.  **Web Service**:
    *   Command: `gunicorn -w 4 -b ::5000 "app:create_app()"` (Default)
    *   Exposes Port 5000.

2.  **Worker Service**:
    *   Command: `python scripts/async_worker.py`
    *   **CRITICAL**: Must wait for DB before starting. Recommended: `python scripts/wait_for_db.py && python scripts/async_worker.py`

### Environment Variables
*   `DATABASE_URL`: Postgres Connection String.
*   `STRIPE_SECRET_KEY`: Live key (sk_live_...) for Prod.
*   `APP_STAGE`: `prod` (Enforces safety checks).

## 3. Release Process

1.  **Verify**: Run `scripts/check_release_clean.py`.
2.  **Build**: Run `python scripts/build_release_zip.py --profile prod`.
    *   Output: `releases/insite_signs_release_prod_<date>.zip`
3.  **Deploy**: Upload zip to hosting provider or push git tag.

### Cleanup Cron
To enable automatic cleanup of expired properties/previews:
1. Set `CRON_TOKEN` in Railway variables (generate a secure random string).
2. Configure a scheduled job (e.g. via GitHub Actions or an external cron service like EasyCron/Mergent) to POST to:
   `https://<your-app-url>/admin/cron/cleanup-expired`
   Header: `X-CRON-TOKEN: <your-token>`

Example CURL:
```bash
curl -X POST https://insite-signs.up.railway.app/admin/cron/cleanup-expired \
  -H "X-CRON-TOKEN: secret_value_here"
```
