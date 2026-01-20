# Product Enhancement Implementation Summary

## What Was Implemented ✅

### 1. Critical Security: Agent Profile Protection
- ✅ Created `order_agent_snapshot` table for immutable agent data per order
- ✅ Implemented Rules A/B/C in `/submit` route:
  - Rule A: Authenticated owners can update their agent profiles
  - Rule B: Guests/non-owners cannot modify owned agent records
  - Rule C: Unowned agents are only updated by authenticated users claiming them
- ✅ Agent snapshots created for all orders ensuring rendering immutability
- ✅ `get_agent_data_for_order()` helper with fallback chain (snapshot → agents table)

### 2. Filename & Path Hardening
- ✅ Created `utils/filenames.py` with:
  - `slugify_text()` - Strict [a-z0-9_-] allowlist, max 60 chars
  - `make_sign_asset_basename()` - Deterministic safe filenames with LAYOUT_VERSION
  - `get_order_asset_dir()` - Per-order directory creation
  - Path resolution helpers for legacy/new structures
- ✅ Added `LAYOUT_VERSION = 1` to constants.py for cache busting

### 3. Preview Optimization
- ✅ Rewrote `utils/pdf_preview.py`:
  - WebP output format (85% quality) for smaller file sizes
  - Max 1800px dimension with aspect ratio preservation
  - Atomic generation using temp files
  - Per-order directory support
  - Backward-compatible `render_pdf_to_png_preview()` maintained

### 4. Interactive Size Selector
- ✅ Created `POST /api/orders/<order_id>/resize` endpoint:
  - Strict access control (owner OR session-bound guest token)
  - Order locking for paid/fulfilled statuses
  - Atomic PDF + preview regeneration
  - Structured error codes: `invalid_size`, `unauthorized`, `order_locked_paid`, `render_failed`
- ✅ Updated `assets.html` with:
  - Size dropdown selector
  - Download PDF button
  - Order status badge
  - Locked state handling
- ✅ Updated `assets.js` with:
  - Resize functionality
  - Error handling with dropdown revert
  - Loading states
- ✅ Added CSS styles for new UI elements

### 5. 36x18 Layout Consistency
- ✅ Verified `_draw_landscape_split_layout()` in pdf_generator.py:
  - Left 50%: Agent headshot + property info + contact
  - Right 50%: Large QR code
  - Proper margins and gutter spacing
  - Preview renders directly from PDF ensuring match

### 6. Timestamp Consistency
- ✅ Updated `routes/agent.py` to use `datetime.now(timezone.utc)` for `guest_token_created_at`
- ✅ Consistent UTC datetime storage

### 7. Size Normalization
- ✅ All code paths use `normalize_sign_size()`:
  - `/submit` route
  - Resize endpoint
  - Stripe price lookup
  - PDF generator routing

### 8. Order Status & Admin Recovery
- ✅ Updated `routes/admin.py`:
  - Retry now works for both `paid` and `print_failed` orders
  - Reset `print_failed` to `paid` before retry attempt
  - Better error messages showing fulfillment_error
- ✅ Status display on assets page with colored badges

### 9. QA & Cleanup
- ✅ Created `scripts/render_samples.py` for visual QA:
  - Renders all sizes to `static/generated/debug_samples/`
  - Supports order ID or sample data
- ✅ Deprecated `utils/sign_generator.py` with notice

## Database Changes

### New Table: order_agent_snapshot
```sql
CREATE TABLE IF NOT EXISTS order_agent_snapshot (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER UNIQUE NOT NULL,
    name TEXT NOT NULL,
    brokerage TEXT NOT NULL,
    email TEXT NOT NULL,
    phone TEXT,
    photo_filename TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (order_id) REFERENCES orders (id)
);
```

**Migration**: Non-destructive `CREATE TABLE IF NOT EXISTS` - app boots cleanly whether table exists or not. Existing orders without snapshots fall back to agents table.

## Files Modified

| File | Change Type | Purpose |
|------|-------------|---------|
| `constants.py` | MODIFY | Added `LAYOUT_VERSION = 1` |
| `database.py` | MODIFY | Added `order_agent_snapshot` table and helpers |
| `utils/filenames.py` | NEW | Safe filename generation utilities |
| `utils/pdf_preview.py` | REWRITE | WebP output, aspect ratio preservation, atomic generation |
| `routes/agent.py` | MODIFY | Agent security rules, snapshots, UTC timestamps |
| `routes/orders.py` | MODIFY | Resize endpoint with access control |
| `routes/admin.py` | MODIFY | print_failed retry support |
| `templates/assets.html` | MODIFY | Size dropdown, PDF download, status badge |
| `static/js/assets.js` | REWRITE | Resize handler, error recovery |
| `static/css/pages/assets.css` | MODIFY | New UI element styles |
| `scripts/render_samples.py` | NEW | QA rendering script |
| `utils/sign_generator.py` | DEPRECATE | Added deprecation notice |

## Verification Checklist

| # | Test Case | Expected Result |
|---|-----------|-----------------|
| 1 | Guest submits form with existing owned agent email | Order created, agent profile NOT modified |
| 2 | Authenticated owner submits with their email | Agent profile updated normally |
| 3 | Guest submits with unowned agent email | Agent snapshot stored on order |
| 4 | PDF filename with special chars (/, \, :) | Filename safe, no path errors |
| 5 | Assets page loads with 36x18 sign | Preview loads quickly, WebP format |
| 6 | Change size dropdown to 24x36 | Preview + PDF link update, no page reload |
| 7 | Try resize on paid order | Dropdown disabled, error message shown |
| 8 | 36x18 PDF opened in viewer | Left 50% headshot+info, Right 50% QR |
| 9 | Admin retries print_failed order | Status resets to paid, fulfillment attempted |
| 10 | Stripe checkout uses correct price for size | Price matches selected size |
| 11 | App boots with fresh database | All tables created, no errors |
| 12 | App boots with existing database (no snapshot table) | Table created, app works |

## Manual QA Commands

```bash
# Run existing tests
python -m pytest test_backend.py -v

# Render sample signs for visual QA
python scripts/render_samples.py

# Start app and test manually
python app.py
```

## Future Enhancements (TODO)

- [ ] Allow paid order "clone as new draft" for design changes
- [ ] Migrate existing orders to use per-order directory structure
- [ ] Add progress indicator during resize operation
- [ ] Email notification when order status changes
