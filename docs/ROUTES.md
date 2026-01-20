# Application Routes

## Public
- `GET /` (Landing Page)
- `GET /r/<code>` (QR Redirect - Analytics)
- `GET /go/<id>` (Agent Redirect - Analytics)
- `GET /about`, `/privacy`, `/terms`

## Auth
- `GET/POST /auth/login`
- `GET/POST /auth/register`
- `GET /auth/verify-email`
- `GET /auth/logout`

## Dashboard (Authenticated)
- `GET /dashboard` (Overview)
- `GET /dashboard/leads`
- `GET /dashboard/properties/<id>/edit`
- `GET /account` (Settings)

## Agent / Orders
- `GET/POST /agent/submit` (Create Property & Sign Order)
- `GET /order/preview/<id>` (Sign Preview)
- `GET /order/success` (Sign Payment Confirmation - Read Only)

## Billing
- `GET /billing` (Subscription Plans)
- `POST /billing/checkout` (Start Subscription Session)
- `POST /billing/unlock-listing/<id>` (Start One-time Unlock Session)
- `GET /billing/success` (Subscription Confirmation - Read Only)
- `GET /billing/portal` (Stripe Customer Portal)

## API (Internal/Worker)
- `POST /stripe/webhook` (Payment Processing & Fulfillment Trigger)

### Print Jobs (Worker API)
- `POST /api/print-jobs/claim?limit=<N>` (Atomically claim queued jobs) (Auth: Bearer Token)
- `GET /api/print-jobs/<job_id>/pdf` (Download job PDF) (Auth: Bearer Token)
- `POST /api/print-jobs/<job_id>/downloaded` (ACK download complete) (Auth: Bearer Token)
- `POST /api/print-jobs/<job_id>/printed` (Mark printed/fulfilled) (Auth: Bearer Token)
