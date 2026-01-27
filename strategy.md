# strategy.md — InSite Signs: Single Source of Truth
**Last updated:** 2026-01-27  
**Scope:** Monetization + SmartSigns Option B strict + Kits + Fulfillment + Analytics/UX (Phase 5)

---

## 0) Non-negotiables (Invariants)

1) **Redirects are internal-only**
- `/r/<code>` resolves only to an internal hosted property page (`/p/<slug>`) or an internal neutral page.
- No external redirect targets.

2) **SmartSigns = Option B strict**
- Normal users cannot manually create SmartSign assets.
- SmartSign assets are created + activated only on **paid SmartSign purchase** (webhook-confirmed).
- Cancellation = freeze (QR keeps working; reassignment disabled).

3) **One canonical paid/entitlement definition**
- Canonical paid statuses: `paid`, `submitted_to_printer`, `fulfilled`.
- No scattered `status == 'paid'` business logic.

4) **Manual fulfillment stays viable**
- Worker claims jobs atomically, downloads PDFs with auth, writes:
  - `/opt/insite_print_worker/inbox/<job>.pdf`
  - `/opt/insite_print_worker/inbox/<job>.json`

5) **Analytics must be accurate and non-PII**
- Buyer PII never goes into event payload analytics.
- Dashboards show aggregated counts and trends; lead details are in lead management views.

---

## 1) What we sell (Monetization Model)

### 1.1 Pro Subscription (control plane)
Pro unlocks:
- unlimited active listings
- SmartSign management (assign/reassign activated assets)
- analytics dashboards
- kit generation (policy: included or limited/month; implementation detail)

### 1.2 One-time purchases
- `listing_unlock`: unlocks property
- `listing_kit`: unlocks kit generation/download (does NOT unlock property)
- `sign`: physical sign order (counts as paid property unlock if in PAID_STATUSES)
- `smart_sign`: SmartSign purchase (creates + activates asset; counts as paid property unlock if in PAID_STATUSES)

---

## 2) Canonical Paid State

### 2.1 PAID_STATUSES
`PAID_STATUSES = {"paid","submitted_to_printer","fulfilled"}`

### 2.2 Property is paid/unlocked if any:
- user subscription active/trialing OR
- order exists for property with:
  - `order_type in ('listing_unlock','sign','smart_sign')`
  - `status in PAID_STATUSES`

`listing_kit` never unlocks property access.

---

## 3) Routing Behavior

### 3.1 `/p/<slug>` — property page (public views)
- Records **page view**:
  - legacy insert into `property_views`
  - canonical event `app_events.property_view`

### 3.2 `/r/<code>` — QR scan entrypoint
- Records **scan**:
  - insert into `qr_scans`
- SmartSigns:
  - if unassigned: show neutral page and track `app_events.smart_sign_scan`

---

## 4) Events & Analytics (Canonical Definitions)

### 4.1 Canonical metric definitions
- **Scan**: row in `qr_scans` (hit to `/r/<code>`)
- **Page View**: row in `property_views` (hit to `/p/<slug>`)
- **Contact Intent**: `app_events` with `event_type='cta_click'`
- **Lead**: persisted lead submission (and/or `app_events.lead_submitted success=true`)

### 4.2 Required event taxonomy
Server events (examples):
- `property_view`
- `lead_submitted` (payload includes success boolean + error_code, no PII)
- `smart_sign_scan`

Client events (allowlist):
- `cta_click` with payload `{ type: request_info|tour|call|email }`

### 4.3 Analytics requirements
Dashboards MUST show:
- scans, views, contact intents, leads
- last 7d counts + previous 7d counts + WoW delta
- per-listing funnel: scans → views → CTA clicks → leads
- insight strings must be explainable by shown numbers (no black box)

### 4.4 No PII rule
- `app_events` payload is PII-stripped and must remain so.
- Analytics pages must not render buyer_email/phone/message.
- Lead detail pages may show lead PII to the owning agent only.

---

## 5) Dashboard UX (Phase 5 requirements)

### 5.1 Primary navigation
Dashboard must have:
- Today (action feed)
- Listings (table with 7d metrics)
- Leads (pipeline)
- SmartSigns
- Kits

### 5.2 “Today” action feed
Cards derived from existing telemetry:
- Listings with 0 scans in 7d
- Listings with scans up >50% WoW
- CTA clicks >0 but leads = 0 in 7d
- SmartSigns unassigned
- Kits ready to download

Each card links to the relevant object.

### 5.3 Listing row requirements
For each listing show:
- 7d scans, 7d views, 7d leads, 7d contact intents
- WoW delta
- last activity timestamp

---

## 6) Listing Kits (Async)

Status model:
- `queued → generating → ready | failed`

Generation MUST be async (not in request thread).
Entitlement: Pro OR `listing_kit` order in PAID_STATUSES.

---

## 7) SmartSigns (Option B strict)

- No normal-user manual asset creation.
- Paid webhook creates and activates the asset.
- Assign/reassign requires:
  - Pro active/trialing
  - activated asset
  - not frozen
- Cancel Pro:
  - freeze assets (resolver keeps working)
  - reassignment disabled

---

## 8) Acceptance Criteria (Definition of Done)

### Analytics/UX Phase 5 DoD
- Dashboard no longer conflates scans with views.
- Listings table shows 7d scans/views/CTA/leads and WoW deltas.
- Property analytics page exists with funnel + 14d trend + CTA breakdown.
- “Today” action feed exists and is driven by real data.
- No PII leaks into analytics views.

### Existing platform DoD
- `/r/<code>` internal-only
- Freeze logic uses canonical paid logic
- Worker claim/download/write flow stable
- Kits async with correct statuses
