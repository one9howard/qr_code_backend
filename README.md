# QR Code Real Estate Business

A Flask-based SaaS for generating QR code lawn signs for real estate agents.

## Features
- **Agent Dashboard**: Manage properties and track scans.
- **QR & PDF Generation**: Automatically generate print-ready PDFs.
- **Stripe Integration**: Subscription-gated dashboard and one-time sign purchases.

## Security Notice

> [!CAUTION]
> **Never include `.env` in release packages or version control.** The `.env` file contains secrets including Stripe API keys.
>
> **If keys are leaked:**
> 1. Rotate keys immediately in [Stripe Dashboard](https://dashboard.stripe.com/apikeys)
> 2. Update `.env` on all servers
> 3. Review Stripe access logs for unauthorized usage
> 4. Regenerate `SECRET_KEY` and `PRINT_SERVER_TOKEN`

Use the release builder script (`python scripts/build_release_zip.py`) to create clean release packages.

> [!IMPORTANT]
> **Deployment Hygiene**:
> - ALWAYS use the release script. NEVER zip the folder manually.
> - Manual zips often include `.git/`, `.venv/`, or `__pycache__/`, which bloat the deployment and can cause failures.
> - The release script automatically excludes all non-production artifacts.

## Setup (Python 3.13 + pip-tools)

This project uses [pip-tools](https://pip-tools.readthedocs.io/) for reproducible dependency management.

### Quick Start (Windows)

```powershell
# Create and activate venv
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies
python -m pip install -U pip setuptools wheel
python -m pip install pip-tools
pip-sync requirements.txt requirements-dev.txt

# Run tests
pytest -q
```

### Quick Start (Linux/macOS)

```bash
# Create and activate venv
python3.13 -m venv .venv
source .venv/bin/activate

# Install dependencies
python -m pip install -U pip setuptools wheel
python -m pip install pip-tools
pip-sync requirements.txt requirements-dev.txt

# Run tests
pytest -q
```

### Local testing (Docker Postgres)

To run tests locally using Docker for the database (Windows compatible):

**Hostname Note:**
- Use `localhost` when running on your host machine (as below).
- Use `db` (the service name) only when running *inside* docker-compose.

```powershell
docker run --name insite-pg -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=insite_test -p 5432:5432 -d postgres:16

$env:DATABASE_URL="postgresql://postgres:postgres@localhost:5432/insite_test"
python migrate.py
pytest -q

# Cleanup
docker rm -f insite-pg
```

### Environment Configuration

```bash
cp .env.example .env
# Edit .env and fill in your values
```

> **⚠️ NEVER commit `.env` to version control!** It contains secrets.

### Upgrading Dependencies

Only edit `requirements.in` or `requirements-dev.in`, then regenerate lockfiles:

```bash
pip-compile --resolver=backtracking --generate-hashes --strip-extras \
  -o requirements.txt requirements.in

pip-compile --resolver=backtracking --generate-hashes --strip-extras \
  -o requirements-dev.txt requirements-dev.in

# Test the upgrade
pytest -q

# Commit lockfiles
git add requirements*.txt
git commit -m "Upgrade dependencies"
```

### Required Environment Variables

- `SECRET_KEY` - Flask session secret (generate with `python -c "import secrets; print(secrets.token_hex(32))"`)
- `STRIPE_SECRET_KEY` - From Stripe Dashboard
- `STRIPE_WEBHOOK_SECRET` - From Stripe CLI or Dashboard
- See `.env.example` for full list.

### Database

The application requires a PostgreSQL database.
Migrations run automatically via Alembic.
Refer to `docker-compose.yml` for a local Postgres instance.


## Stripe Integration

To enable subscriptions and physical product checkout:

1.  **Stripe Account**: Create a Stripe account and get your API keys.
2.  **Environment Variables**: Copy `.env.example` to `.env` and fill in:
    *   `STRIPE_SECRET_KEY` & `STRIPE_PUBLISHABLE_KEY`
    *   `STRIPE_WEBHOOK_SECRET` (from the CLI listen command below)
    *   `STRIPE_PRICE_MONTHLY`, `STRIPE_PRICE_ANNUAL`, `STRIPE_PRICE_SIGN` (Create these products in Stripe)

3.  **Local Webhook Testing**:
    *   Install Stripe CLI.
    *   Run: `stripe listen --forward-to localhost:5000/stripe/webhook`
    *   Copy the webhook signing secret (whsec_...) to your `.env` or `config.py`.

4.  **Testing Flow**:
    *   **Subscription**: Register a new user -> Click Dashboard -> Pay with Stripe Test Card (4242...) -> Verify access.
    *   **Physical Sign**: Create a property -> Click "Order Physical Lawn Sign" -> Pay -> Check server logs for "Fulfillment Submitted".

## Known-Good Manual Test Script
To verify the Stripe integration end-to-end:

1.  **Start Stripe Listener**:
    ```powershell
    stripe listen --forward-to http://127.0.0.1:5000/stripe/webhook
    ```
    *(Take the webhook secret and put it in `.env`)*

2.  **Start App**:
    ```powershell
    $env:FLASK_ENV = "development"
    python app.py
    ```

3.  **Browser Test**:
    *   Go to `http://localhost:5000`
    *   Register `test@example.com`
    *   **Verify**: You are redirected to the Landing Page (Home) and remain logged in.
    *   Click "Dashboard" -> **Verify**: Redirects to subscription required page (with blurred background).
    *   Click "Monthly" -> Redirects to Stripe -> Pay
    *   **Check Console**: Look for `[Webhook] User ... subscription active.`
    *   Refresh Dashboard -> Should work.
    *   Create Property -> Assets Page -> "Order Physical Lawn Sign" -> Redirects to Stripe -> Pay
    *   **Check Console**: Look for `[Webhook] Order ... paid.` followed by `[Fulfillment] Submitting ...`


## Running the App

```bash
python app.py
```

## Print Fulfillment Worker
The print worker claims jobs and downloads PDFs for local printing:
```bash
python scripts/print_worker.py
```

## Production Deployment

### Local & Home Server
1. **Docker (Recommended)**
   ```powershell
   docker build -t qrapp .
   docker run -p 8000:8000 --env-file .env qrapp
   ```

2. **Python Venv**
   ```powershell
   # Windows
   .\.venv\Scripts\Activate.ps1
   $env:FLASK_ENV = "production"
   python app.py
   ```

3. **Home Server (Systemd)**
   If running on a Linux home server, use the provided unit file in `systemd/`:
   ```bash
   sudo cp systemd/qrapp.service /etc/systemd/system/
   sudo systemctl enable --now qrapp
   ```

   **Required Environment Variables (Production/Home Server):**
   - `SECRET_KEY`: Random string
   - `STRIPE_SECRET_KEY`: From Stripe Dashboard
   - `BASE_URL`: Public URL (e.g., `https://signs.myhome.com`)
   - `DATABASE_URL`: **Required.** (e.g., `postgresql://user:pass@host:5432/dbname`)

**Important:** Secrets (like `STRIPE_SECRET_KEY`, `DATABASE_URL`) must be set via `copilot secret init`. See `REPORT_DEPLOYMENT_READINESS.md` for full details.

### Manual / Virtual Machine (Legacy)

### Environment Variables (Required)
For production deployment, the following environment variables **must** be set:

- `SECRET_KEY` - Flask secret key for session management (generate a random string)
- `STRIPE_SECRET_KEY` - Stripe API secret key
- `STRIPE_PUBLISHABLE_KEY` - Stripe publishable key
- `STRIPE_WEBHOOK_SECRET` - Stripe webhook signing secret
- `STRIPE_PRICE_MONTHLY`, `STRIPE_PRICE_ANNUAL`, `STRIPE_PRICE_SIGN` - Stripe price IDs
- `BASE_URL` - Your production URL (e.g., https://yourdomain.com)

See `.env.example` for a complete template.

### Order Status Flow
The application uses the following order statuses:

1. **pending_payment** - Order created, awaiting payment
2. **paid** - Payment successful, awaiting fulfillment
3. **submitted_to_printer** - Successfully submitted to print server
4. **print_failed** - Print submission failed (will retry via Stripe webhook)
5. **fulfilled** - (Reserved for future delivery confirmation)

- Use **1-2 gunicorn workers**

### Local Testing

To run tests locally, you must run a Postgres container.

1. Start Postgres:
   ```bash
   docker run --name qrapp-db -e POSTGRES_PASSWORD=postgres -p 5432:5432 -d postgres
   ```

2. Run Tests:
   (Windows PowerShell)
   ```powershell
   $env:DATABASE_URL="postgresql://postgres:postgres@localhost:5432/qrapp"; python -m pytest
   ```
   (Bash)
   ```bash
   export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/qrapp
   python -m pytest
   ```
- For higher concurrency, consider migrating to PostgreSQL
- WAL mode is enabled automatically on database connection

### Webhook Idempotency & Retry Behavior
Stripe webhook events are tracked in the `stripe_events` table with status-based idempotency:
- **received** - Event is being processed
- **processed** - Event was successfully handled (subsequent deliveries are ignored)
- **failed** - Processing failed (Stripe retries will attempt reprocessing)

This ensures that if fulfillment fails (e.g., print server unreachable), returning HTTP 500 triggers Stripe to retry the webhook, and the retry will reprocess the event.

### Checkout Session Idempotency
The subscription checkout flow uses attempt-based idempotency to prevent Stripe "same key different params" errors:

- **New attempts**: Each checkout creates a new `checkout_attempts` record with a unique idempotency key
- **Retry semantics**: Double-clicks or network retries with the same `attempt_token` return the existing Stripe session
- **Param change detection**: If request parameters change between attempts, a new attempt is automatically created
- **Webhook tracking**: Completed checkouts are marked in the `checkout_attempts` table via webhook

The `checkout_attempts` table tracks all checkout attempts with their status, idempotency key, params hash, and Stripe session ID.

### Sign Size Pricing
Physical sign prices vary by size. The app uses Stripe **Lookup Keys** to dynamically select the correct price:

| Size | Lookup Key | Env Override |
|------|------------|--------------|
| 12x18 | `12x18_sign` | `STRIPE_LOOKUP_KEY_SIGN_12X18` |
| 18x24 | `18x24_sign` | `STRIPE_LOOKUP_KEY_SIGN_18X24` |
| 24x36 | `24x36_sign` | `STRIPE_LOOKUP_KEY_SIGN_24X36` |
| 36x18 | `36x18_sign` | `STRIPE_LOOKUP_KEY_SIGN_36X18` |

**Setup in Stripe Dashboard:**
1. Create a separate **Product** for each size (e.g., "Lawn Sign 24x36").
2. Add a **Price** to each product.
3. Set the **Lookup Key** on each price (e.g., `24x36_sign`).
4. Ensure all products are **Active** (not archived).

**Verification:** Run `python scripts/verify_stripe_prices.py` to confirm all mappings work.

### File Upload Security
- Maximum upload size: 16MB
- Allowed image types: PNG, JPG, JPEG, WEBP
- All uploads are validated and sanitized
- File extensions are preserved correctly

## Security Configuration

### CSRF Protection
The application uses Flask-WTF CSRF protection for all HTML forms:
- All POST forms include a hidden `csrf_token` field: `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">`
- JSON endpoints (like `/order-sign`) accept CSRF token via `X-CSRFToken` header
- The Stripe webhook endpoint (`/stripe/webhook`) is exempted from CSRF checks (server-to-server)

**Templates updated:**
- `submit.html`, `login.html`, `register.html`, `billing.html`, `dashboard.html`, `edit_property.html`, `admin_orders.html`

### Session Cookie Hardening
Session cookies are hardened with the following settings (configured in `config.py`):

| Setting | Value | Notes |
|---------|-------|-------|
| `SESSION_COOKIE_HTTPONLY` | `True` | Prevents JavaScript access |
| `SESSION_COOKIE_SAMESITE` | `Lax` | Allows OAuth/Stripe redirects |
| `SESSION_COOKIE_SECURE` | `True` (prod only) | HTTPS only in production |
| `REMEMBER_COOKIE_HTTPONLY` | `True` | Protects remember-me cookies |
| `REMEMBER_COOKIE_SECURE` | `True` (prod only) | HTTPS only in production |

Production mode is detected via `FLASK_ENV=production` environment variable.

## Upgrade Flow

### Routes
- `/billing` - Main subscription page (shows pricing or manage subscription)
- Dashboard "UPGRADE" button links directly to `/billing`

### Dashboard Features by Tier

| Feature | Free Tier | Pro Tier |
|---------|-----------|----------|
| Create Properties | ✅ | ✅ |
| Order Physical Signs | ✅ | ✅ |
| Basic Stats (Listings, Scans) | ✅ | ✅ |
| Pro Analytics Panel | 🔒 Locked | ✅ |
| 7-Day Scan Trends | 🔒 | ✅ |
| Top Property Stats | 🔒 | ✅ |

Free users see a blurred preview of Pro analytics with an "Upgrade to Pro" call-to-action.

## Developer Notes

### Running Locally
```bash
# Install dependencies
pip install -r requirements.txt

# Set development environment
$env:FLASK_ENV = "development"  # Windows PowerShell
export FLASK_ENV=development    # Linux/Mac

# Run the app
python app.py
```

### Manual QA Checklist
After making changes, verify these flows:

**1. Start & Auth**
- [ ] Landing page loads correctly without errors
- [ ] Register new user logic works (redirects to home, auto-login)
- [ ] Login/Logout works correctly
- [ ] Dashboard shows user details

**2. Sign Creation & Validation**
- [ ] `/submit` page loads with new styles (external CSS)
- [ ] Color picker works and updates visual selection
- [ ] **Validation Test**: Try submitting with invalid hex color (via DevTools). Should revert to default.
- [ ] **Validation Test**: Try submitting with invalid size. Should revert to default.

**3. Physical Sign Checkout (Stripe Idempotency)**
- [ ] Create a property & generate sign assets.
- [ ] Click "Order Physical Lawn Sign".
- [ ] Verify redirection to Stripe Checkout.
- [ ] **Idempotency Test**: Click "Back", then click "Order" again. Should reuse the *same* Stripe session (check logs/URL).
- [ ] **Param Change Test**: Change sign size/color for the same order, click "Order" again. Should create a *new* Stripe session.
- [ ] Complete payment with Stripe Test Card (4242...).
- [ ] Verify redirection to success page.
- [ ] **Webhook Verification**: Check server logs for:
    - `[Webhook] Marking Order ... paid`
    - `[Webhook] Marked sign-order attempt ... as completed`
    - `[Fulfillment] Order ... fulfilled successfully`

**4. Subscription Flow**
- [ ] Go to `/billing`.
- [ ] Select a plan -> Redirects to Stripe.
- [ ] Complete payment.
- [ ] Verify webhook processes subscription and updates user status.

**5. Technical Checks**
- [ ] **CSRF**: Verify `X-CSRFToken` header is present in network requests for `/order-sign`.
- [ ] **Env Gating**: Verify `/dev` routes return 404 in production mode (if tested in prod).
- [ ] **Build**: Run `scripts/build_release_zip.py` and verify `templates` folder is copied correctly.

## Print Server

The print server is now a separable service located in `services/print_server`.

**Run locally (Dev):**
```bash
python -m services.print_server
```

**Run in Production:**
Require `PRINT_SERVER_TOKEN` environment variable.
```bash
export PRINT_SERVER_TOKEN="secure-token-here"
python -m services.print_server
```

**Compatibility:**
Legacy `python print_server.py` command is supported but deprecated.

## Print Preflight

PDF generation now includes automatic preflight checks for POD compliance (Bleed, QR Size, Quiet Zone).

**Run Demo/Verification:**
```bash
python scripts/print_preflight_demo.py
```
This generates test PDFs in `instance/preflight_demo_output/`.
#   q r _ c o d e _ b a c k e n d 
 
 