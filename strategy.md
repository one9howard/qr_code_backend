# strategy.md — InSite Signs: Single Source of Truth (Hybrid Monetization + SmartSign Option B Strict)

**Last updated:** 2026-01-27  
**Owner:** Product + Engineering  
**Scope:** Monetization rules, entitlements, SmartSign (Reusable Sign Assets) MVP, Digital Listing Kit MVP, and fulfillment/print pipeline.

## 0) Non-negotiables (Invariants)

1) **Redirects are internal-only.**
   - `/r/<code>` may only resolve to a hosted property page in our app (`/p/<slug>`).
   - No external URLs in MVP. Ever.

2) **SmartSigns follow Option B strict.**
   - **NO manual creation** of SmartSign assets in the dashboard for normal users.
   - A SmartSign asset is created **only** as part of a **paid SmartSign purchase**.
   - Activation is not a UI toggle; it is set by the purchase/webhook.

3) **Cancellation uses Freeze, not disable.**
   - SmartSign QR keeps working and continues to resolve to the last assigned property page.
   - Reassignment is disabled while frozen (subscription canceled / not active).
   - Freeze must not “accidentally expire” properties that are paid via orders.

4) **One canonical paid/entitlement source.**
   - There is exactly one function/module that defines:
     - what “paid property access” means
     - what counts as “paid order”
     - what “subscription active” means
     - the canonical “paid statuses” set  
   - No scattered `status == "paid"` checks.

5) **Manual fulfillment stays viable.**
   - Print jobs are claimed atomically, PDFs downloaded with auth, and written with JSON sidecars to:
     - `/opt/insite_print_worker/inbox/*.pdf`
     - `/opt/insite_print_worker/inbox/*.json`

---

## 1) Product Model (What we sell)

We monetize via **hybrid** model:

### 1.1 Pro Subscription (Control plane)
**Pro** unlocks:
- unlimited active listings (no expiry lockouts)
- analytics UI
- SmartSign management (assign/reassign) **for activated SmartSigns**
- Listing kit generation included (or limited/month; implementation detail)

### 1.2 One-time purchases (Transactional)
- **Listing Unlock** (`order_type = listing_unlock`)  
  Grants paid access to the property (not a subscription, not Pro).
- **Digital Listing Kit** (`order_type = listing_kit`)  
  Grants kit generation + download for that property.
- **Property-specific sign** (`order_type = sign`)  
  Does NOT grant Pro. May or may not unlock property page depending on business rules (see entitlements).

### 1.3 Physical SmartSign (Premium reusable sign)
- **SmartSign purchase** (`order_type = smart_sign`) creates + activates one reusable SmartSign asset.
- Pro is required to reassign it.
- If Pro cancels: freeze behavior applies.

---

## 2) Core Entities & Tables

### 2.1 `sign_assets` (Reusable SmartSigns)
Fields:
- `id`
- `user_id`
- `code` (unique, permanent; used in `/r/<code>`)
- `label` (optional)
- `active_property_id` (nullable)
- `activated_at` (NOT NULL for real SmartSigns; set only by purchase flow)
- `activation_order_id` (links to the smart_sign order)
- `is_frozen` (bool; set when subscription not active)
- timestamps

### 2.2 `sign_asset_history`
- `sign_asset_id`, old/new property, user who changed it, time

### 2.3 `listing_kits`
- `property_id`, `user_id`
- `status`: `queued|generating|ready|failed`
- `kit_zip_key`, `assets_json`
- `purchased_at` (nullable)
- timestamps

### 2.4 `print_jobs`
- Must support atomic claim by worker(s)
- PDF stored in object storage; worker downloads via authenticated endpoint

---

## 3) Routing: `/r/<code>` Resolver

Resolution order (must not regress legacy behavior):

1) If `code` matches `sign_assets.code`:
   - If `active_property_id` is set: redirect to `/p/<slug>` for that property.
   - If unassigned: show neutral “Not assigned” page (no external redirect).
2) Else: fall back to legacy QR/campaign behavior (existing implementation).

**Security constraints:**
- No query parameter may override destination.
- No external redirect targets.

---

## 4) Entitlements & Paid State (Canonical Definitions)

### 4.1 Canonical paid statuses
Define once (e.g., `PAID_STATUSES`) and reuse everywhere:

- `paid`
- `submitted_to_printer`
- `fulfilled`

Anything else is NOT paid.

### 4.2 Property “paid access” sources
A property is considered **paid/unlocked** if ANY are true:

1) Subscription is active or trialing (Pro)
2) There exists an order for that property with:
   - `order_type in ('listing_unlock', 'sign', 'smart_sign')`
   - `status in PAID_STATUSES`

**Explicitly NOT a property unlock:**
- `listing_kit` does **not** unlock the property page.

> Rule: do not write ad-hoc queries for “paid” in random files. Always use the canonical helper(s).

### 4.3 SmartSign management entitlement
Assign/reassign a SmartSign requires ALL:
- Subscription is active/trialing (Pro)
- SmartSign is activated (`activated_at` is set)
- SmartSign is not frozen (`is_frozen == false`)

---

## 5) Freeze Behavior (Cancellation model)

When Pro becomes inactive (canceled, unpaid, etc.):

- Set `sign_assets.is_frozen = true` for that user.
- Reassignment endpoints must reject with clear error.
- `/r/<code>` continues to resolve normally to last `active_property_id`.

When Pro becomes active again:
- Set `is_frozen = false` and reassignment works again.

### 5.1 Critical safety rule: freeze must not “expire paid properties”
Freeze logic MUST use the canonical property paid logic:
- If a user cancels Pro, we may mark properties as expired/unpaid **only if** they are not paid via orders under `PAID_STATUSES`.
- Absolutely no `status == 'paid'` checks in freeze paths.

---

## 6) SmartSign Option B Strict Implementation Rules

### 6.1 No manual creation for normal users
- The dashboard may list assets and allow assignment **only for activated assets**.
- There is no “Create SmartSign” button for normal users.
- If we need manual creation for admins/dev:
  - it must be behind an explicit admin flag
  - and must produce an activated asset only when explicitly requested

### 6.2 Asset creation & activation
- A paid SmartSign order must:
  - create a `sign_assets` row (or reuse an existing reserved row if designed)
  - set `activated_at`
  - link `activation_order_id`
  - optionally queue print job(s) for fulfillment

### 6.3 Assignment flows
- Default state after purchase: asset exists and is activated; it may be:
  - unassigned until user assigns to a property, OR
  - auto-assigned if the checkout flow includes a property choice
- `/r/<code>` for unassigned shows “Not assigned” page.

---

## 7) Digital Listing Kit Architecture (MVP)

### 7.1 Deliverables bundle
- Print-ready sign PDF (existing)
- Flyer PDF (new)
- Social square (1080×1080)
- Story/reel (1080×1920)
- Zip containing all assets
- Owner-only download from dashboard

### 7.2 Generation must be async
Generation MUST NOT run synchronously in a web request handler.

Required flow:
- `/api/kits/<property_id>/start` creates kit row with `status=queued`
- background worker/job transitions:
  - `queued -> generating -> ready` OR `failed`
- dashboard polls or refreshes status

Entitlement to generate/download:
- Pro (active/trialing), OR
- property has `listing_kit` order with `status in PAID_STATUSES`

---

## 8) Fulfillment / Print Worker (Must remain stable)

### 8.1 API contract
- Claim endpoint is atomic (one job claimed per worker call, no duplicates)
- Download endpoint requires auth token
- ACK endpoint marks job as downloaded/processed

### 8.2 Worker outputs
Writes to:
- `/opt/insite_print_worker/inbox/<print_job_id>.pdf`
- `/opt/insite_print_worker/inbox/<print_job_id>.json`

Sidecar JSON must include:
- order id
- shipping name/address
- SKU / product metadata
- property id (if relevant)
- timestamps

---

## 9) Build Phases (Strict priority)

### Phase 0 — Stop regressions & protect revenue
- Canonicalize entitlements + paid statuses everywhere (eliminate `status == 'paid'` drift)
- Ensure freeze logic cannot expire paid-via-order properties
- Keep print pipeline deterministic and idempotent

### Phase 1 — SmartSign MVP (Option B strict)
- `/r/<code>` resolver supports `sign_assets`
- “Not assigned” neutral page
- Dashboard:
  - list activated SmartSigns
  - assign/reassign (Pro-only) with history tracking
- Scan logging ties to `sign_asset_id`

### Phase 2 — SmartSign purchase integration
- Paid SmartSign order creates + activates asset
- (Optional) select property at checkout; otherwise assign later
- Webhook validates idempotency and handles retries safely

### Phase 3 — Digital Listing Kit MVP
- Async generation + zip download
- Purchase kit a la carte
- Pro includes kit generation

### Phase 4 — Guardrails for profitability
- free plan listing limits
- upgrade prompts at pain points
- basic conversion + retention metrics

---

## 10) Acceptance Criteria (Definition of Done)

### 10.1 SmartSigns: Resolver & internal-only
- `/r/<asset_code>`:
  - if assigned → redirects to `/p/<slug>` only
  - if unassigned → shows “Not assigned”
- Legacy QR/campaign behavior still works when code is not in `sign_assets`

### 10.2 SmartSigns: Option B strict enforcement
- Normal user UI has **no manual SmartSign create**
- SmartSign assets appear only after SmartSign purchase
- Assign/reassign requires:
  - Pro active/trialing
  - activated asset
  - not frozen

### 10.3 Freeze correctness
- After Pro cancellation:
  - reassignment denied
  - resolver still redirects to last assigned property
- No paid-via-order property is incorrectly expired due to status mismatch:
  - freeze paths use canonical paid logic (PAID_STATUSES)

### 10.4 Listing Kit async
- Start endpoint returns quickly; generation happens out-of-band
- Status transitions are persisted and observable
- Zip download works only for entitled user

### 10.5 Fulfillment pipeline
- Paid sign order queues exactly one print_job (idempotent)
- Two workers cannot claim the same job
- Worker writes PDF + JSON sidecar with required fields

---

## 11) Engineering “No Excuses” Checks (greps + tests)

These are hard gates during review:

- Grep gate: no scattered paid checks
  - `grep -R "status == 'paid'" -n .` must return **nothing** (or only in the canonical paid module where it defines the set)
- Grep gate: no manual SmartSign creation routes in normal UI
  - ensure “Create SmartSign” UI and endpoints are removed or admin-guarded
- Test gate:
  - unit tests for paid logic (`PAID_STATUSES`)
  - unit tests for freeze using canonical paid logic
  - integration tests for `/r/<code>` resolver precedence and internal-only redirect
