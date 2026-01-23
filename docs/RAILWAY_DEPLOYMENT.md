# Railway Staging Deployment Guide

This guide provides step-by-step instructions to deploy the InSite Signs application to **Railway** as a staging environment at `https://staging.insitesigns.com`.

> **IMPORTANT**: This staging environment uses **test-mode only**. The application will **crash on startup** if any `sk_live_` or `pk_live_` keys are configured when `APP_STAGE=test`.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Part A — Railway Service Configuration](#part-a--railway-service-configuration)
3. [Part B — Custom Domain + DNS (GoDaddy)](#part-b--custom-domain--dns-godaddy)
4. [Part C — Stripe Test-Mode Webhook Setup](#part-c--stripe-test-mode-webhook-setup)
5. [Operator Runbook (Copy/Paste)](#operator-runbook-copypaste)

---

## Prerequisites

- **Railway Account**: [railway.app](https://railway.app/)
- **GitHub Repository**: This repo connected to Railway
- **AWS Account**: S3 bucket created (private access only)
- **Stripe Account**: Test mode enabled
- **GoDaddy Account**: DNS management access for `insitesigns.com`

---

## Part A — Railway Service Configuration

### A1. Build Method

This application uses **Dockerfile deploy**. Railway will automatically detect and use the `Dockerfile` in the repository root.

**PORT Binding Verification**:
The Dockerfile CMD uses shell-form which correctly expands `$PORT`:

```dockerfile
CMD ["sh", "-c", "gunicorn --workers 3 --bind 0.0.0.0:${PORT} --access-logfile - --error-logfile - app:app"]
```

✅ No changes needed. Railway injects `PORT` automatically.

---

### A2. Start Command

**No custom start command required**. The Dockerfile handles it correctly.

If Railway asks for a start command, use:
```
sh -c "gunicorn --workers 3 --bind 0.0.0.0:${PORT} --access-logfile - --error-logfile - app:app"
```

---

### A3. Environment Variables (Staging)

Configure these in Railway: **Service → Variables**

#### Core Application
| Variable | Value | Notes |
|----------|-------|-------|
| `APP_STAGE` | `test` | **REQUIRED** - Enables safety rails |
| `FLASK_ENV` | `production` | Triggers production checks |
| `BASE_URL` | `https://staging.insitesigns.com` | No trailing slash |
| `SECRET_KEY` | `<generate-random-64-char>` | Use `openssl rand -hex 32` |
| `PRINT_JOBS_TOKEN` | `<any-secure-token>` | Can use same generation method. Also accepts `PRINT_SERVER_TOKEN` as alias. |

#### Database
| Variable | Value | Notes |
|----------|-------|-------|
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` | Railway reference syntax |

> **To add Postgres**: Right-click canvas → Add → Database → PostgreSQL

> [!IMPORTANT]
> **DATABASE_URL is REQUIRED** for production/staging deployments. The `migrate.py` script will **exit with error** if DATABASE_URL is not set, preventing invalid configuration.

#### Proxy Headers
| Variable | Value | Notes |
|----------|-------|-------|
| `TRUST_PROXY_HEADERS` | `true` | Railway uses reverse proxy |
| `PROXY_FIX_NUM_PROXIES` | `1` | Single proxy layer |

#### S3 Storage
| Variable | Value | Notes |
|----------|-------|-------|
| `STORAGE_BACKEND` | `s3` | Enables S3 storage |
| `S3_BUCKET` | `insitesigns-staging` | Your bucket name |
| `AWS_REGION` | `us-east-1` | Bucket region |
| `S3_PREFIX` | `staging/` | Optional folder prefix |
| `AWS_ACCESS_KEY_ID` | `AKIA...` | IAM user credentials |
| `AWS_SECRET_ACCESS_KEY` | `<secret>` | IAM user credentials |

#### Stripe (TEST MODE ONLY)
| Variable | Value | Notes |
|----------|-------|-------|
| `STRIPE_SECRET_KEY` | `sk_test_...` | **MUST start with `sk_test_`** |
| `STRIPE_PUBLISHABLE_KEY` | `pk_test_...` | **MUST start with `pk_test_`** |
| `STRIPE_WEBHOOK_SECRET` | `whsec_...` | From Stripe webhook endpoint |

> ⚠️ **SAFETY RAIL**: If you set `sk_live_*` or `pk_live_*` with `APP_STAGE=test`, the app will crash with:
> ```
> SAFETY RAIL: Attempted to use Live Stripe Secret Key in 'test' stage!
> ```

#### Filesystem
| Variable | Value | Notes |
|----------|-------|-------|
| `INSTANCE_DIR` | `/app/instance` | **Recommended**. Persists instance data (uploads, cached artifacts). |

#### Email (SMTP) - Optional for Staging
| Variable | Value | Notes |
|----------|-------|-------|
| `SMTP_HOST` | `smtp.gmail.com` | Required for lead notifications in PROD |
| `SMTP_USER` | `email@example.com` | |
| `SMTP_PASS` | `<app-password>` | |
| `NOTIFY_EMAIL_FROM` | `no-reply@...` | Optional |

#### Stripe Pricing
Print pricing is resolved via Stripe *Price lookup keys* only (no STRIPE_PRICE_* env vars for prints).

You must create active Stripe Products + Prices with the lookup keys required by the app (see `services/print_catalog.py`).
Subscription pricing still uses env vars:

| Variable | Value |
|----------|-------|
| `STRIPE_PRICE_MONTHLY` | `price_xxxxx` |
| `STRIPE_PRICE_ANNUAL` | `price_xxxxx` |

---

### A4. Database Migrations

The application uses gated migrations via `RUN_MIGRATIONS_ON_STARTUP`.

#### Option 1: One-Time Manual Run (Recommended for Staging)

After your first deploy, run migrations manually:

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login
railway login

# Link to your project
railway link

# Run migration command
railway run python migrate.py
```

#### Option 2: Automatic on Startup (Single Instance Only)

Set this environment variable:
```
RUN_MIGRATIONS_ON_STARTUP=true
```

> ⚠️ **WARNING**: Only safe for single-instance deployments. Multiple instances will race on migrations.

---

### A5. Verification

After deploy, verify the app is responding:

```bash
curl https://staging.insitesigns.com/healthz
```

Expected response:
```json
{"status": "ok", "db": "connected"}
```

---

## Part B — Custom Domain + DNS (GoDaddy)

### B1. Railway: Add Custom Domain

1. Go to your Railway service
2. Click **Settings** → **Networking** section
3. Click **+ Custom Domain**
4. Enter: `staging.insitesigns.com`
5. Railway will display a target like: `abc123xyz.up.railway.app`
6. **Copy this value** for the next step

---

### B2. GoDaddy: Add CNAME Record

1. Log in to [GoDaddy](https://www.godaddy.com/)
2. Go to **My Products** → **DNS** for `insitesigns.com`
3. Click **Add Record**
4. Configure:
   - **Type**: `CNAME`
   - **Host**: `staging`
   - **Points to**: `abc123xyz.up.railway.app` (from Railway)
   - **TTL**: 1 Hour (or default)
5. Click **Save**

**DNS Propagation**: Can take 5 minutes to 48 hours. Typically completes within 30 minutes.

#### Verify DNS Propagation

```bash
# Windows PowerShell
nslookup staging.insitesigns.com

# macOS/Linux
dig staging.insitesigns.com CNAME
```

Expected output should show the Railway target.

---

### B3. TLS/HTTPS Verification

Railway automatically provisions TLS certificates. After DNS propagates:

1. **Check Railway Dashboard**: Green checkmark on domain indicates cert issued
2. **Test HTTPS**:
   ```bash
   curl -I https://staging.insitesigns.com/healthz
   ```
   Should return `HTTP/2 200`

3. **Verify BASE_URL**: Ensure absolute URLs in the app are correct by submitting a test property and checking the generated QR code URL.

---

## Part C — Stripe Test-Mode Webhook Setup

### C1. Webhook Endpoint

The webhook route is:
```
POST /stripe/webhook
```

This endpoint:
- Is **CSRF exempt** (registered in `app.py`)
- Requires `STRIPE_WEBHOOK_SECRET` to verify signatures
- Processes events idempotently via `stripe_events` table

---

### C2. Register Webhook in Stripe Dashboard

1. Go to [Stripe Dashboard](https://dashboard.stripe.com/)
2. **Ensure Test Mode is enabled** (toggle in top-right)
3. Navigate: **Developers** → **Webhooks**
4. Click **+ Add endpoint**
5. Configure:
   - **Endpoint URL**: `https://staging.insitesigns.com/stripe/webhook`
   - **Events to send**: See C4 below
6. Click **Add endpoint**

---

### C3. Obtain Signing Secret

1. After creating the endpoint, click on it
2. Under **Signing secret**, click **Reveal**
3. Copy the `whsec_...` value
4. In Railway Variables, set:
   ```
   STRIPE_WEBHOOK_SECRET=whsec_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```
5. **Redeploy** the service (Railway auto-redeploys on variable change)

> ⚠️ **Common Failure**: Using the wrong signing secret (e.g., from a different endpoint or live vs test mode).

---

### C4. Events to Subscribe To

Based on the application's webhook handler, subscribe to these events:

| Event | Purpose |
|-------|---------|
| `checkout.session.completed` | Handles subscription activation & sign order payment |
| `invoice.paid` | Renews subscription status |
| `customer.subscription.updated` | Syncs subscription status changes |
| `customer.subscription.deleted` | Marks subscription as cancelled |

---

### C5. Verification Checklist

- [ ] **Test Checkout Flow**:
  1. Create a test property on staging
  2. Click "Order Physical Sign"
  3. Complete checkout with Stripe test card: `4242 4242 4242 4242`
  
- [ ] **Check Stripe Dashboard**:
  - Go to **Developers** → **Webhooks** → Your endpoint
  - Verify **Recent deliveries** shows `200` responses

- [ ] **Check Application Logs**:
  - In Railway: **Deployments** → **View Logs**
  - Look for: `[Webhook] Event xxx processed successfully`

- [ ] **Verify Database**:
  - Check `stripe_events` table has the event with `status='processed'`
  - Check `orders` table has `status='paid'` for the order

---

## Operator Runbook (Copy/Paste)

### Railway Environment Variables

```env
# Core
APP_STAGE=test
FLASK_ENV=production
INSTANCE_DIR=/app/instance
BASE_URL=https://staging.insitesigns.com
SECRET_KEY=<run: openssl rand -hex 32>
PRINT_JOBS_TOKEN=<run: openssl rand -hex 16>

# Database (use Railway reference)
DATABASE_URL=${{Postgres.DATABASE_URL}}

# Proxy
TRUST_PROXY_HEADERS=true
PROXY_FIX_NUM_PROXIES=1

# Migrations (optional, single-instance only)
RUN_MIGRATIONS_ON_STARTUP=true

# S3 Storage
STORAGE_BACKEND=s3
S3_BUCKET=insitesigns-staging
AWS_REGION=us-east-1
S3_PREFIX=staging/
AWS_ACCESS_KEY_ID=<from AWS IAM>
AWS_SECRET_ACCESS_KEY=<from AWS IAM>

# Stripe (TEST MODE)
STRIPE_SECRET_KEY=sk_test_<your-key>
STRIPE_PUBLISHABLE_KEY=pk_test_<your-key>
STRIPE_WEBHOOK_SECRET=whsec_<from-stripe-endpoint>
```

### GoDaddy CNAME Record

| Field | Value |
|-------|-------|
| Type | CNAME |
| Host | `staging` |
| Points to | `<your-railway-target>.up.railway.app` |
| TTL | 1 Hour |

### Stripe Webhook Endpoint

| Field | Value |
|-------|-------|
| URL | `https://staging.insitesigns.com/stripe/webhook` |
| Mode | Test |
| Events | `checkout.session.completed`, `invoice.paid`, `customer.subscription.updated`, `customer.subscription.deleted` |

### Post-Deploy Verification Commands

```bash
# Health check
curl https://staging.insitesigns.com/healthz

# DNS verification
nslookup staging.insitesigns.com

# TLS check
curl -I https://staging.insitesigns.com
```

---

## Security Notes

- **No live Stripe keys**: Safety rails will crash the app
- **S3 bucket is private**: Uses presigned URLs for access
- **No secrets in git**: All sensitive values are environment variables
- **Database isolation**: Staging uses separate Railway Postgres instance
