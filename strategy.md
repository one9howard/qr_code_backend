# strategy.md — InSite Signs / Property Protocol: Hybrid Monetization + Reusable SmartSign MVP

**Document purpose:** This is the single source of truth for the next build phase. It captures product decisions, monetization rules, and the MVP engineering roadmap for “Reusable Sign Assets” (SmartSigns) + Digital Listing Kit, aligned to a **hybrid** revenue model.

**Non-negotiable outcome:** Ship a retention-centric SaaS that creates switching costs through reusable QR sign assets, while still monetizing one-off purchases (listing unlock + digital kit + physical signs).

---

## 1) Executive Summary

We are building a real estate analytics + lead-capture SaaS where QR codes route to hosted property pages (`/p/<slug>`). The platform monetizes via:

1) **Pro subscription** (recurring): unlocks management, reassignment of reusable QR assets, analytics, unlimited active listings, and kit generation (as included value).
2) **One-time purchases** (transactional):  
   - **Listing Unlock** (digital) per property  
   - **Digital Listing Kit** (deliverables bundle) per property  
3) **Physical sign orders** (margin):  
   - Property-specific yard signs  
   - Premium reusable **SmartSign metal sign** tied to a reusable SignAsset

The core product wedge is **Reusable Sign Assets** (SmartSigns): one permanent QR code per physical sign that can be reassigned in the dashboard (Pro-only). On cancellation, the sign **freezes**: it keeps working (still redirects to the last assigned property page) but cannot be changed without reactivating Pro.

---

## 2) Hard Product Decisions (Already Chosen)

### 2.1 Redirect policy
- **Redirects are INTERNAL ONLY.**  
- A SignAsset may only resolve to a hosted property page in our system (`/p/<slug>`).
- No external URLs in MVP. This avoids abuse, compliance headaches, and support churn.

### 2.2 Cancellation behavior
- **Freeze is the cancellation model.**
  - QR continues to resolve to the last assigned hosted property page indefinitely.
  - Reassignment is disabled unless Pro is active again.
  - Analytics UI is disabled for canceled users, but logging may continue server-side.

### 2.3 Multi-sign office buyers
- Agents can own multiple SignAssets (e.g., office buys 4).
- We adopt **Option B** for pricing/entitlement: **one-time activation entitlement per sign**, with Pro required to manage/reassign.

### 2.4 Digital Listing Kit positioning
- We are not “selling a PDF.”  
- We sell a **Digital Listing Kit**: an outcome-oriented deliverables bundle.

---

## 3) Monetization & Packaging (Recommended)

### 3.1 Pro subscription (software control plane)
**Target pricing:** $29/mo or $249/yr (start here unless you enjoy operating at a loss).

Includes:
- Unlimited active listings (no expiry lockouts)
- Analytics: scans, views, leads (and conversion funnel)
- Lead management workflow features already in the app
- Campaigns/variants (optional; keep if already stable)
- **SmartSign management** for activated assets: assign/reassign destinations
- **Digital Listing Kit generation** (included or limited/month)

### 3.2 One-time purchases (hybrid)
1) **Listing Unlock**: $9–$19 / property  
   - Unlocks the paid experience for that property (not just “un-expire”)
   - Does **not** grant SmartSign reassignment privileges

2) **Digital Listing Kit (a la carte)**: $15–$29 / property  
   - Kit generation + zip download (deliverables listed below)

### 3.3 Physical signs (margin)
- Yard sign (property-specific): optional, lower margin
- **Premium SmartSign metal sign**: $179–$249 each  
  - Includes **one-time activation** of a reusable SignAsset
  - Pro required to reassign; cancellation freeze applies

---

## 4) MVP Feature Definitions

### 4.1 Reusable Sign Assets (“SmartSigns”)
**Entity:** `sign_assets`

Core behavior:
- Each asset has a permanent QR route: `/r/<asset_code>`
- The asset points to **one active property** at a time (internal hosted property page)
- Pro users can reassign any time
- If unassigned: show a neutral “Not assigned” page (no external redirect)

**On cancellation:** freeze (redirect continues to last destination; changes disabled).

### 4.2 Digital Listing Kit
**Deliverables bundle for a property:**
- Print-ready sign PDF (already exists)
- Flyer PDF (new)
- Social square image (1080×1080)
- Story/reel image (1080×1920)
- Optional open house variation (future)
- Zip file containing all assets
- Stored + downloadable from dashboard (owner-only)

---

## 5) Engineering Architecture (MVP)

### 5.1 Data model (tables)
**New**
- `sign_assets`
  - id, user_id, code (unique), label
  - active_property_id (nullable)
  - activated_at (nullable) — set on physical SmartSign purchase
  - activation_order_id (nullable)
  - is_frozen (bool) — toggled by subscription state
  - created_at, updated_at

- `sign_asset_history`
  - id, sign_asset_id
  - old_property_id, new_property_id
  - changed_by_user_id
  - changed_at

**New for kit**
- `listing_kits`
  - id, property_id, user_id
  - status: pending|ready|failed
  - kit_zip_key
  - assets_json (storage keys)
  - purchased_at (nullable)
  - created_at, updated_at

### 5.2 Routing resolver: `/r/<code>`
Resolution order (must not break existing):
1) If code matches `sign_assets.code`: redirect to its `active_property_id` hosted page  
2) Else fall back to existing behavior: campaign variants / legacy property QR codes

### 5.3 Entitlements (canonical)
One function must decide paid state across the app. No scattered checks.

Paid sources for a property:
1) Subscription active/trialing (Pro) → paid via subscription
2) Paid order `order_type='listing_unlock'` → paid via listing unlock
3) Paid order `order_type='sign'` → paid via sign order

**Important:** Listing unlock must unlock paid features, not just clear expiry.

### 5.4 Freeze behavior (non-predatory, but sticky)
When Pro cancels:
- `sign_assets.is_frozen = true` for that user
- Assets still redirect
- Reassignment endpoints refuse changes
- Analytics UI hidden (but server-side logging can continue)

### 5.5 Manual fulfillment stays intact (until POD integration)
The physical sign pipeline must remain viable without POD API:
- Print jobs are queued in DB + PDF stored in storage
- A worker script claims jobs atomically, downloads PDFs with auth, writes to:
  - `/opt/insite_print_worker/inbox/*.pdf`
  - `/opt/insite_print_worker/inbox/*.json`
- Manual printing remains possible via `ls -l` + sidecar manifests

---

## 6) Roadmap & Build Phases (Strict Priority)

### Phase 0 — Stop regression and operational breakage
- Print job API: add atomic claim endpoint + authenticated PDF download endpoint
- Version-control worker script + systemd unit installer
- Add tests + CI (GitHub Actions) for critical flows

**Why:** If payments and fulfillment regress, you don’t have a business—just refunds.

### Phase 1 — Reusable Sign Assets MVP (SmartSigns)
- Add tables + migrations
- Implement `/r/<code>` resolver for sign assets (internal-only)
- Dashboard UI: create asset (Pro-only), list assets, assign/reassign
- Log scans to `sign_asset_id` (minimal analytics: count)

### Phase 2 — Option B activation + physical SmartSign product
- Metal SmartSign order flow creates asset + activates it (activated_at)
- Webhook: on paid sign order, activate asset + queue print job
- Enforce: reassignment requires Pro + activated + not frozen

### Phase 3 — Digital Listing Kit MVP
- Generate flyer PDF + social assets + zip
- Store keys + allow download from dashboard
- Sell kit a la carte via Stripe checkout (order_type='listing_kit')
- Pro includes kit generation (entitlement)

### Phase 4 — Business guardrails (profitability)
- Free plan max active listings enforced (already planned/partially implemented)
- Clear upgrade prompts in dashboard at the moment of pain (expiry, second listing, kit generation, reassignment)
- Basic cohort metrics: conversion, retention, kit attach rate, sign attach rate

---

## 7) Acceptance Criteria (Definition of Done)

### Reusable Sign Assets
- Create SignAsset (Pro-only) and see it in dashboard
- Assign to a hosted property page (Pro-only)
- Scan `/r/<asset_code>` redirects only to `/p/<slug>` (no external)
- Unassigned asset shows “Not assigned” page
- History records every reassignment

### Freeze on cancellation
- Cancel Pro:
  - reassignment disabled
  - asset continues redirecting to last assigned property
- Reactivate Pro:
  - reassignment enabled again

### Digital Listing Kit
- Pro user can generate kit and download zip
- Non-Pro can purchase kit, then generate/download
- Kit includes PDF flyer + correct QR + social images

### Fulfillment / manual workflow
- Paid sign order → exactly one print_job queued (idempotent)
- Worker claims jobs atomically → no duplicates with two workers
- Worker downloads PDF with auth and writes to `/opt/insite_print_worker/inbox`
- Sidecar JSON contains shipping and order metadata

---

## 8) Risks & Mitigations (Blunt)

1) **If Pro is underpriced**, you will subsidize storage, support, chargebacks, and printing ops.  
   - Mitigation: do not race to the bottom. Price for sustainability.

2) **If cancellation makes signs “dead,”** you will trigger chargebacks and negative reviews.  
   - Mitigation: freeze, do not hard-lock.

3) **If entitlements are inconsistent across routes/templates,** users will see “paid but locked” states.  
   - Mitigation: one canonical entitlement function; remove hardcoded `== 'active'` checks.

4) **If print jobs are not atomic-claimed,** you will get duplicates, missed jobs, and chaos.  
   - Mitigation: `/claim` endpoint with SKIP LOCKED; worker uses it.

---

## 9) Immediate Next Step (Next Build Sprint)

**Implement Phase 0 first.**  
Do not start SmartSign assets until:
- atomic claim + auth PDF download are in place,
- worker script is version-controlled and documented,
- tests + CI exist for webhook + fulfillment guard.

Once Phase 0 is stable, proceed to Phase 1 (SignAssets MVP).

---

## 10) Open Questions (Decide Later, Not Now)

- Whether “assigned-to-sign_asset” properties remain publicly visible indefinitely after cancel (recommended: yes, but analytics off).
- Whether Pro includes X SmartSign activations or only management (Option B suggests activation is per physical sign purchase).
- Whether kit generation should be limited per month to control costs (likely yes if usage spikes).
