# Smoke Test - Ubuntu Deployment

## Prerequisites
- Python 3.13+


- Postgres database accessible  
- `.env` file with DATABASE_URL set (or environment variable)

## 1. Install Dependencies

### Quick Path (Recommended for dev):
```bash
pip install -r requirements_simple.txt
```

### Strict Path (For production/CI):
```bash
pip install -r requirements.txt
```

**Expected**: No errors about "tomli not pinned" or missing hashes.

**Verify**:
```bash
pip list | grep tomli  # Should show tomli if Python < 3.11
```

---

## 2. Run Migrations

### With DATABASE_URL (Production/Staging):
```bash
# Ensure DATABASE_URL is set in .env or environment
python migrate.py
```

**Expected Output**:
```
[Manage] Loaded .env file
[Manage] DATABASE_URL format: postgresql://postgres:****@host:port/db
[Manage] Detected DATABASE_URL, using Alembic for Postgres...
[Manage] Alembic migration to 'head' successful.
[Manage] Database migration completed successfully.
```

**Should NOT see**:
- "No DATABASE_URL, using legacy SQLite"
- `PRAGMA busy_timeout` errors
- Any Postgres syntax errors

### Without DATABASE_URL (Should Fail):
```bash
# Remove DATABASE_URL from .env and environment
unset DATABASE_URL
python migrate.py
```

**Expected Output**:
```
[Manage] ERROR: DATABASE_URL environment variable is not set.
[Manage]
[Manage] For production/staging: Set DATABASE_URL in your environment:
[Manage]   export DATABASE_URL=postgresql://user:pass@host:5432/dbname
[Manage]
[Manage] For local SQLite development (legacy):
[Manage]   export FORCE_SQLITE=1
[Manage]   python migrate.py
```

**Expected**: Script exits with code 1

---

---

## 3. Local Dev (Postgres)

SQLite is no longer supported. Use Docker Compose for local Postgres:

```bash
docker compose up -d
# Ensure .env has DATABASE_URL=postgresql://manual...
python migrate.py
```

---

## 4. Start Application

### Development:
```bash
python app.py
```

### Production (with Gunicorn):
```bash
gunicorn -c gunicorn.conf.py app:app
# or
gunicorn --bind 0.0.0.0:8080 app:app
```

**Expected**: No errors, server starts successfully

---

## 5. Verify Health Check

```bash
# Development server (port 5000)
curl http://localhost:5000/healthz

# Gunicorn (port 8080 or configured PORT)
curl http://localhost:8080/healthz
```

**Expected Response**:
```json
{"status": "ok", "db": "connected"}
```

---

## 6. Verify No PRAGMA-on-Postgres Errors

This test ensures that if someone accidentally calls `init_db()` with a Postgres connection, it gracefully exits without running SQLite PRAGMA statements.

**Test Script** (`test_pragma_safety.py`):
```python
#!/usr/bin/env python3
import os
# Force Postgres URL
os.environ['DATABASE_URL'] = 'postgresql://test:test@localhost/test_db'
# Ensure no FORCE_SQLITE
os.environ.pop('FORCE_SQLITE', None)

from app import create_app
from database import init_db

app = create_app()
try:
    init_db(app)
    print("✓ init_db with Postgres connection did not crash")
except Exception as e:
    if "PRAGMA" in str(e).upper():
        print(f"✗ PRAGMA error detected: {e}")
        exit(1)
    # Other errors are fine for this test (e.g., connection refused)
    print(f"⚠ Other error (expected if DB not available): {e}")
```

**Run**:
```bash
python test_pragma_safety.py
```

**Expected**: No PRAGMA-related errors (warnings about DB connection are acceptable)

---

## Success Criteria

- ✅ `pip install -r requirements.txt` succeeds without "tomli not pinned" error
- ✅ `migrate.py` with DATABASE_URL runs Alembic successfully
- ✅ `migrate.py` without DATABASE_URL exits with error
- ✅ No PRAGMA errors when using Postgres
- ✅ App starts and `/healthz` returns 200 with Postgres connection

## 7. Verify Print Job Lifecycle

Simulate a print worker lifecycle using curl.

**1. Create a dummy print job (if none exist)**
(Requires running app and DB access, or just trigger a sign order via webhook test)

**2. List & Claim Jobs**
```bash
# Replace TOKEN with your PRINT_SERVER_TOKEN (see .env)
# Returns JSON with job details and "pdf_download_url"
curl -H "Authorization: Bearer TOKEN" http://localhost:5000/api/print-jobs
```

**3. Test PDF Download**
Using the `pdf_download_url` from above (or manually constructing):
```bash
curl -H "Authorization: Bearer TOKEN" -O http://localhost:5000/api/print-jobs/<job_id>/pdf
```
**Expected**: Saves `print_job_<job_id>.pdf` locally.

**4. Mark as Printed**
```bash
curl -X POST -H "Authorization: Bearer TOKEN" http://localhost:5000/api/print-jobs/<job_id>/printed
```
**Expected**: `{"success": true}` and order status updates to `fulfilled`.

---

## 8. Verify Stripe Webhook Idempotency (Mock)

Since you cannot generate a valid Stripe signature without the CLI/Key, verify the logic:
1. Ensure `stripe_events` table exists.
2. Review logs when hitting the endpoint (will fail signature in dev without CLI).
3. If testing with Stripe CLI: `stripe listen --forward-to localhost:5000/stripe/webhook`. Trigger `checkout.session.completed`. Expect one processing log even if triggered twice.

### 3. Verify Print Job (Atomic Claim)

**List & Claim Pending Job:**
```bash
# Claim job (simulating worker)
curl -X POST "$BASE_URL/api/print-jobs/claim?limit=1" \
     -H "Authorization: Bearer $PRINT_TOKEN"
```
*Expected*: JSON list containing the job with `download_url` and status `claimed`.

**Download PDF:**
```bash
# Use job_id from above
curl -O -J -H "Authorization: Bearer $PRINT_TOKEN" "$BASE_URL/api/print-jobs/<JOB_ID>/pdf"
```
*Expected*: .pdf file download.

**ACK Download:**
```bash
curl -X POST "$BASE_URL/api/print-jobs/<JOB_ID>/downloaded" \
     -H "Authorization: Bearer $PRINT_TOKEN"
```
*Expected*: `{"success": true}`

**Mark Printed:**
```bash
curl -X POST "$BASE_URL/api/print-jobs/<JOB_ID>/printed" \
     -H "Authorization: Bearer $PRINT_TOKEN"
```
*Expected*: `{"success": true}` (Order status -> fulfilled)

### 4. Verify Worker Service (If installed)
On the print server:
```bash
sudo systemctl status insite-worker
journalctl -u insite-worker -f
```
*Expected*: Logs showing "Claimed 1 jobs", "Downloading...", "Acked".Success Criteria

- ✅ `pip install -r requirements.txt` succeeds without "tomli not pinned" error
- ✅ `migrate.py` with DATABASE_URL runs Alembic successfully
- ✅ `migrate.py` without DATABASE_URL exits with error (unless FORCE_SQLITE=1)
- ✅ No PRAGMA errors when using Postgres
- ✅ App starts and `/healthz` returns 200 with Postgres connection
- ✅ Print Job API claims jobs, serves PDFs, and updates status correctly
- ✅ Manual Fulfillment script exports files and updates DB
- ✅ Webhook handles idempotency (if testing with CLI)

## Rollback Plan

If issues arise:
1. **Requirements**: `git checkout requirements.txt requirements.in`
2. **Migrate.py**: `git checkout migrate.py`
3. **Database.py**: `git checkout database.py`

## 10. Production Readiness Verification (Manual)

### Entitlements & Gating
1. **Active Subscription**: User with active sub should see "Paid via subscription" on all properties.
2. **Paid Order**: User without sub but with paid Sign Order should see "Paid via sign_order" for that property.
3. **Free/Expired**: 
   - New property (no sub/order) -> Active (Free).
   - Cancelled sub -> All non-ordered properties should show "Expired" (frozen).

### Stripe Webhooks & Freeze
1. **Freeze**: Cancel a subscription in Stripe (test mode). Verify user's properties (without headers) now show `expires_at` in the past (locked).
2. **Attempt Token**: Verify logs show `Marked attempt <token> as completed`.

### Print Job Safety
1. **Concurrency**: Run `api/print-jobs` from two terminals simultaneously. Ensure no duplicate job IDs.
2. **Manual Export**: Run `scripts/export_print_jobs_to_inbox.py`. Verify filenames are strictly `<job_id>.pdf`.
