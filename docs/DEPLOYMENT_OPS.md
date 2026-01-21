# Safe Staging & Deployment Operations

## Overview
This repo is configured for "Safe Staging".
- **Test Env**: Uses Stripe Test Mode (fake money). `APP_STAGE=test`.
- **Prod Env**: Uses Stripe Live Mode (real money). `APP_STAGE=prod`.

## 1. Environments & Safety Rails

### Test Environment (`test`)
- **Stripe Keys**: Must start with `sk_test_` / `pk_test_`.
- **Price IDs**: Must be Test Mode Price IDs.
- **Safety**: If you try to use `sk_live_` keys here, the app will crash on startup to protect you.

### Production Environment (`prod`)
- **Stripe Keys**: Must start with `sk_live_` / `pk_live_`.
- **Safety**: `APP_STAGE=prod` overrides the test default in `manifest.yml`.

## 2. Secrets Management
Each environment needs its own set of secrets stored in AWS SSM via Copilot.

**Required Secrets:**
- `SECRET_KEY`: High-entropy string.
- `DATABASE_URL`: Postgres connection string.
- `STRIPE_SECRET_KEY`: `sk_test_...` (for test) / `sk_live_...` (for prod).
- `STRIPE_PUBLISHABLE_KEY`: `pk_test_...` (for test) / `pk_live_...` (for prod).
- `STRIPE_WEBHOOK_SECRET`: Signing secret from Stripe Dashboard.
- `PRINT_JOBS_TOKEN`: Secure token.
- `STRIPE_PRICE_MONTHLY`, `STRIPE_PRICE_ANNUAL`, etc. (Matching the environment).

## 3. Migration Workflow
Migrations are **disabled on startup** (`RUN_MIGRATIONS_ON_STARTUP=false`) to prevent accidents.
Run them manually as a one-off task after deployment (or set the var to `true` temporarily).

**Run Migration Command:**
```bash
copilot task run \
  --app insite \
  --env test \
  --image <ECR_IMAGE_URI> \
  --command "python3 migrate.py" \
  --secrets DATABASE_URL=/copilot/insite/test/secrets/DATABASE_URL
```

## 4. Updates After First Deploy
After the first successful deploy, Copilot gives you a URL (e.g., `https://qrapp.test.insite.aws`).

1. **Update `BASE_URL`**:
   In `copilot/qrapp/manifest.yml`, update:
   ```yaml
   variables:
     BASE_URL: https://qrapp.test.insite.aws
   ```
   Then run `copilot deploy --env test`.

2. **Configure Stripe Webhooks**:
   - Go to Stripe Dashboard (Test Mode).
   - Add endpoint: `https://qrapp.test.insite.aws/stripe/webhook`
   - Copy the Signing Secret (`whsec_...`).
   - Update secret:
     ```bash
     copilot secret init --name STRIPE_WEBHOOK_SECRET --values test="whsec_..." --overwrite
     ```
   - Redeploy.
