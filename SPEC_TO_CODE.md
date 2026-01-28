# SPEC_TO_CODE.md — SmartSign Spec-to-Code Mapping (Enforcement Guide)
**Last updated:** 2026-01-28  
**Purpose:** Remove ambiguity. This maps `SPECS.md` fields to code variables and required invariants.

---

## 0) Source of truth
- `SPECS.md` is the authoritative spec.
- `services/pdf_smartsign.py` must implement it exactly.
- Any other generator must match output semantics.

---

## 1) Coordinate system and rectangles

### 1.1 Page and trim
In `services/pdf_smartsign.py`, for a given `size_key`:
- `width_pt = SIGN_SIZES[size_key]['width'] * inch`
- `height_pt = SIGN_SIZES[size_key]['height'] * inch`
- `bleed_pt = 0.125 * inch`

Canvas pagesize must be:
- `(width_pt + 2*bleed_pt, height_pt + 2*bleed_pt)`

All drawing must treat the trim origin as:
- `origin = (bleed_pt, bleed_pt)`

**Definition**
- Trim rect in canvas coordinates:
  - `trim = (bleed_pt, bleed_pt, bleed_pt + width_pt, bleed_pt + height_pt)`

### 1.2 Safe rect
From `SPECS.md` safe margin `safe_pt`:
- `safe = inset(trim, safe_pt)`

**Invariant**
- ALL text bounding boxes must be fully inside `safe` (tolerance ≤ 1 pt).
- QR card must be fully inside `safe`.
- Accent bars and full-bleed backgrounds may extend to trim or bleed; text may not.

---

## 2) Layout dispatch (must be unambiguous)
`layout_id` is read from asset/order context.

Dispatch:
- `smart_v1_photo_banner` → legacy/photo renderer (existing behavior)
- `smart_v1_agent_brand` → Agent Brand renderer
- otherwise → Modern Minimal renderer

**Invariant**
- `smart_v1_agent_brand` must not look like minimal.
- Regression guard required (unit test or smoke test) to ensure dispatch calls the correct renderer.

---

## 3) Modern Minimal mapping (smart_v1_minimal)

### 3.1 Bands
Spec fields used (in inches, convert to pt):
- `top_bar_h`
- `header_band_h`
- `footer_band_h`
- `qr_size`
- `qr_pad`

Rectangles (all in trim coordinates):
- `top_bar = (trim.x0, trim.y1 - top_bar_h, trim.x1, trim.y1)`
- `header_rect = (safe.x0, top_bar.y0 - header_band_h, safe.x1, top_bar.y0)`
- `footer_rect = (safe.x0, safe.y0, safe.x1, safe.y0 + footer_band_h)`
- `qr_zone = (safe.x0, footer_rect.y1, safe.x1, header_rect.y0)`

**Invariant**
- Header content must fit inside `header_rect` and inside `safe`.
- Footer content must fit inside `footer_rect` and inside `safe`.
- QR card must fit inside `qr_zone` and inside `safe`.

### 3.2 Header grid
Within `header_rect`:
- Left column width = 62% of header width
- Gap = 3%
- Right column width = 35%

Variables:
- `hdr_w = header_rect.width`
- `left_w = 0.62 * hdr_w`
- `gap_w = 0.03 * hdr_w`
- `right_w = hdr_w - left_w - gap_w`

Left column contains:
- Name (max 2 lines)
- Phone (1 line)
- Email (1 line, optional/omit if it cannot fit cleanly)

Right column contains:
- Brokerage text (max 2 lines) OR logo if available

### 3.3 Typography
Use the per-size font start/min from `SPECS.md`:
- name, phone, email, brokerage, cta, url

**Required fitter behavior**
- Name/brokerage: use multiline fitter; return block height
- Phone/email: single-line fitter
- Layout must be based on measured block heights, not string length

---

## 4) Agent Brand mapping (smart_v1_agent_brand)

### 4.1 Bands
Spec fields:
- `top_band_h`
- `footer_band_h`
- `qr_size`
- `qr_pad`
- `logo_diameter`

Rectangles:
- `top_band = (trim.x0, trim.y1 - top_band_h, trim.x1, trim.y1)`
- `footer_band = (trim.x0, trim.y0, trim.x1, trim.y0 + footer_band_h)`
- `qr_zone = (safe.x0, footer_band.y1, safe.x1, top_band.y0)`

**Invariant**
- Text elements in top band must remain inside `safe` horizontally (don’t slam to trim edge).
- Footer CTA + URL must remain inside safe and must never overlap.

### 4.2 Top band content zones
Within `safe`-clipped top band area:
- Left: logo/headshot circle (diameter = `logo_diameter`)
- Center: agent name (max 2 lines)
- Right: brokerage text (max 2 lines) or logo

Define zones:
- `left_zone_w = logo_diameter + padding`
- `right_zone_w = brokerage_max_width` (use 35–40% of band width, but must be constrained by safe)
- `center_zone = remaining width`

**Fallbacks**
- If no headshot/logo: draw monogram circle with initials (still same diameter).
- If brokerage absent: omit right zone content cleanly.

### 4.3 Footer CTA rules
Footer content:
- CTA line 1: `SCAN` (white) + `FOR` (accent)
- CTA line 2: `DETAILS` (accent)
- URL below CTA, centered

**Invariant**
- URL baseline must be at least `safe_pt` above trim bottom.
- URL must shrink/ellipsize rather than overflow.

---

## 5) URL correctness (critical)
Printed fallback URL must be:
- `{base_domain}/r/{code}`

Where:
- `base_domain` = `BASE_URL` stripped of scheme and trailing slash.

**Invariant**
- Never print `{base_domain}/{code}` (missing `/r/`).

---

## 6) QR placement (all layouts)
- QR size must be exactly `qr_size` from spec.
- QR must be centered within `qr_zone` unless spec says otherwise.
- QR backing card:
  - width/height = `qr_size + 2*qr_pad`
  - stroke width 2pt
  - radius 0.25"

**Invariant**
- QR card must be inside `safe`.
- Quiet zone must remain pure white.

---

## 7) Automated verification (required)
Add `scripts/verify_smartsign_layouts.py` that:

1) Generates PDFs for all 10 combinations:
- layouts: minimal, agent_brand
- sizes: 12x18, 18x24, 24x36, 36x24
2) Renders previews via `utils/pdf_preview.render_pdf_to_web_preview` for each PDF.
3) Uses PyMuPDF to extract text blocks and asserts each block is within safe rect:
- safe rect must be computed exactly as above.
- tolerance ≤ 1 pt.
4) Exits non-zero on any failure and prints a PASS/FAIL summary table.

Worst-case strings are defined in `SPECS.md`.

---

## 8) Acceptance checklist (what “done” means)
- Layout dispatch correct (agent_brand is visually distinct)
- No overlaps with worst-case strings on any size
- No text outside safe rect on any size
- Printed URL includes `/r/`
- Preview generation succeeds for all 10 outputs
