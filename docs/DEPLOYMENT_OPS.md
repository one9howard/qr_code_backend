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
- **Safety**: `APP_STAGE=prod` must be set in Railway variables.

## 2. Secrets Management
Each environment needs its own set of secrets stored in Railway Variables.

**Required Secrets:**
- `SECRET_KEY`: High-entropy string.
- `DATABASE_URL`: Postgres connection string (Auto-injected by Railway if using a plugin).
- `STRIPE_SECRET_KEY`: `sk_test_...` (for test) / `sk_live_...` (for prod).
- `STRIPE_PUBLISHABLE_KEY`: `pk_test_...` (for test) / `pk_live_...` (for prod).
- `STRIPE_WEBHOOK_SECRET`: Signing secret from Stripe Dashboard.
- `PRINT_JOBS_TOKEN`: Secure token.
- `STRIPE_PRICE_MONTHLY`, `STRIPE_PRICE_ANNUAL`, etc. (Matching the environment).

## 3. Migration Workflow
Migrations are **disabled on startup** (`RUN_MIGRATIONS_ON_STARTUP=false`) to prevent accidents.
Run them manually as a one-off task via the Railway CLI after deployment.

**Run Migration Command:**
```bash
# Connect to your project environment first
railway run python migrate.py
```

## 4. Updates After First Deploy
After the first successful deploy, Railway gives you a URL (e.g., `https://web-production-1234.up.railway.app`).

1. **Update `BASE_URL`**:
   In Railway Dashboard -> Variables, set:
   ```
   BASE_URL=https://web-production-1234.up.railway.app
   ```
   This will trigger a redeploy.

2. **Configure Stripe Webhooks**:
   - Go to Stripe Dashboard (Test Mode).
   - Add endpoint: `https://<YOUR_RAILWAY_URL>/stripe/webhook`
   - Copy the Signing Secret (`whsec_...`).
   - Add variable in Railway:
     ```
     STRIPE_WEBHOOK_SECRET=whsec_...
     ```
   - Redeploy happens automatically.

## 5. Property Page Mobile QA

### Verify Mobile Lead Capture
1. Open any property page on a mobile device (or browser DevTools mobile view)
2. Tap "Request info" in the mobile action bar (bottom of screen)
3. Verify the lead form modal opens (not an upsell/paywall)
4. Fill in the form:
   - Name: "Test User"
   - Email: "test@example.com"
   - Phone: "555-1234"
   - Check consent checkbox
5. Tap "Send request"
6. Verify success message appears
7. Lead should be visible in `/dashboard/leads`

### Test Lead Submission API Directly
```bash
curl -X POST <YOUR_RAILWAY_URL>/api/leads/submit \
  -H "Content-Type: application/json" \
  -d '{
    "property_id": 1,
    "buyer_name": "Test Lead",
    "buyer_email": "test@example.com",
    "consent": true
  }'
# Expected: {"success": true, ...}

# Missing consent -> 400
curl -X POST <YOUR_RAILWAY_URL>/api/leads/submit \
  -H "Content-Type: application/json" \
  -d '{
    "property_id": 1,
    "buyer_name": "Test Lead",
    "buyer_email": "test@example.com"
  }'
# Expected: 400 error - consent required
```

## 6. Client Events QA

### Verify Events Endpoint
```bash
# Valid event
curl -X POST <YOUR_RAILWAY_URL>/api/events \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "cta_click",
    "property_id": 1,
    "payload": {"type": "request_info", "tier": "paid"}
  }'
# Expected: {"success": true}

# Using 'event' alias (backward compatibility)
curl -X POST <YOUR_RAILWAY_URL>/api/events \
  -H "Content-Type: application/json" \
  -d '{
    "event": "gated_content_attempt",
    "property_id": 1,
    "tier": "free"
  }'
# Expected: {"success": true} - tier auto-built into payload

# Valid client events
curl -X POST <YOUR_RAILWAY_URL>/api/events \
  -H "Content-Type: application/json" \
  -d '{"event_type": "upsell_shown", "property_id": 1, "payload": {"trigger": "photos"}}'
# Expected: {"success": true}

# Invalid event type -> 400
curl -X POST <YOUR_RAILWAY_URL>/api/events \
  -H "Content-Type: application/json" \
  -d '{"event_type": "invalid_event", "property_id": 1}'
# Expected: 400 error
```

### Verify Events in Database
```bash
# Connect to remote DB
railway run python -c "from database import get_db; from app import create_app; app=create_app(); ctx=app.app_context(); ctx.push(); db=get_db(); print(db.execute(\"SELECT event_type, property_id, payload, occurred_at FROM app_events WHERE event_type IN ('cta_click', 'gated_content_attempt', 'upsell_shown') ORDER BY occurred_at DESC LIMIT 10;\").fetchall())"
```

### Browser QA Checklist
1. Open property page and open browser DevTools Network tab
2. Click "Request info" → Verify POST to `/api/events` with `cta_click`
3. Click on locked gallery (FREE mode) → Verify POST with `gated_content_attempt`
4. When upsell sheet opens → Verify POST with `upsell_shown`

