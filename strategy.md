# InSite Signs - Strategy & Architecture (Phase 0/1)

**Goal**: Deliver a reliable, premium "Speed to Lead" sign platform for realtors.

## Core Concepts

### 1. Order Types (Canonical)
The system recognizes these `order_type` values as sources of truth:
*   `sign`: A physical sign order. 
    *   differentiated by `print_product` SKU (e.g. `listing_sign_coroplast_18x24`, `smart_sign_aluminum_18x24`).
    *   This is the PRIMARY transaction type.
*   `smart_sign`: Legacy/Specific variant for SmartSigns (being merged into `sign` conceptually, but schema distinct for now).
*   `listing_kit`: Digital-only asset bundle (does NOT unlock property).
*   `listing_unlock`: One-time payment to unlock a property (deprecated in favor of subscriptions, but supported).

### 2. Gating & Entitlements
*   **Property Unlock**: A property is "paid/active" if:
    *   User has Active Subscription (Pro).
    *   User paid for a `sign`, `smart_sign`, or `listing_unlock` for that property.
*   **Listing Kit**: Purchasing a kit enables *generation* of that kit, but does NOT unlock the property itself.

### 3. Fulfillment Pipeline (Async)
*   **Web**: Handles request -> creates DB row -> redirects to Stripe.
*   **Webhook**: Receives payment -> updates DB status -> Enqueues Job.
*   **Worker**: Picks up Job -> Generates PDF -> Sends to Print Provider/Queue.
*   **Wait**: Print Provider callbacks update status to `shipped`.

## Design Philosophy
*   **Aesthetics**: Premium, glassmorphism, high-DPI assets.
*   **Reliability**: Async queues for heavy lifting (PDFs). Idempotent webhooks.
*   **Safety**: Staging vs Prod separation (Stripe Keys, Release Builds).

## Current Phase Goals (Hardening)
1.  **Release Hygiene**: Clean zips, no debug artifacts.
2.  **Canonical Data**: No "fix-up" logic in webhooks. Data is correct at insertion.
3.  **Observability**: Clear logs for every state transition.
