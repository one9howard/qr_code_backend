# SPECS.md — Print + Layout Specifications (Single Source of Truth)

This document is the canonical specification for print products, layouts, sizing, bleed/safe zones,
typography constraints, and preview rendering constraints. Code must either:
1) Load these values directly, or
2) Mirror them exactly and pass `scripts/check_specs_sync.py`.

---

# 1) Canonical Sizes

## 1.1 SmartSign (Purchasable Sizes — Reality A)
SmartSign is purchasable in **3 sizes only**:
- 18x24 (portrait)
- 24x36 (portrait)
- 36x24 (landscape)

Any other SmartSign size must be rejected at:
- UI (dropdown)
- routes validation
- print_catalog validation
- PDF generator dispatch

## 1.2 Listing Sign (Purchasable Sizes)
Listing Sign supports **4 sizes**:
- 12x18 (portrait)
- 18x24 (portrait)
- 24x36 (portrait)
- 36x24 (landscape)

---

# 2) Global Print Rules (All Products)

## 2.1 Units
- 1 inch = 72 points (pt)

## 2.2 Bleed
- Bleed: 0.125" on all sides (unless explicitly overridden per product)

## 2.3 Safe Margins (No critical content beyond)
Safe margin is measured from trim edge inward.

- 12x18: 0.50"
- 18x24: 0.50"
- 24x36: 0.50"
- 36x24: 0.60"

## 2.4 QR Code Rules (Scan Reliability)
- QR must be placed on a solid, high-contrast background.
- QR must have a quiet zone (padding) of at least **0.25"** on all sides.
- If on a dark/colored background, QR must be placed on a **white card** with padding.
- QR should be axis-aligned (no rotation).

## 2.5 Text Fit Rules (No overlaps allowed)
- No layout may allow overlap or clipping.
- When a text block cannot fit:
  1) shrink-to-fit down to min font size,
  2) if still failing, truncate with ellipsis,
  3) if still failing (rare), drop lowest-priority line (email, secondary text).

Priority: Agent Name > Phone > CTA > URL > Brokerage > Email.

---

# 3) SmartSign Layout Specs

## 3.1 Supported Layout IDs
- smart_v1_photo_banner (existing)
- smart_v1_minimal (Agent-First Minimal) — default recommended
- smart_v1_agent_brand (premium variant; secondary)

---

## 3.2 smart_v1_minimal (Agent-First Minimal)

### Visual Structure
1. Header: headshot + name + phone (+ optional brokerage)
2. Center: QR in white rounded card with border + padding
3. Footer: CTA + URL

### Global style
- Background: white
- Accent: optional thin rule only (no heavy color band)
- Email: OFF by default (optional; must not degrade name/phone)

### Size: 18x24 (Portrait)
Trim: 18w × 24h  
Header height: 3.40"  
Footer height: 3.10"  
Accent rule: 0.10" (optional)

Header:
- Headshot: 2.20"
- Headshot inset: 0.25"
- Gap headshot→text: 0.30"
- Name: max 64pt / min 44pt, 2 lines max, leading 1.22
- Phone: max 52pt / min 38pt, single-line
- Brokerage (optional): max 38pt / min 28pt, single-line, right-aligned

QR card:
- QR size: 7.20"
- Card padding: 0.55"
- Card outer: 8.30"
- Radius: 0.35"
- Border: 2pt, #E2E8F0

Footer:
- CTA: max 64pt / min 44pt (prefer 1 line; 2 lines allowed if >= min)
- URL: max 34pt / min 26pt
- Default CTA: “Price + Photos + 3D Tour”
- URL format: insite.co/r/XXXX1234

### Size: 24x36 (Portrait)
Trim: 24w × 36h  
Header: 4.90"  
Footer: 4.40"  
Accent: 0.12"

Header:
- Headshot: 3.10"
- Inset: 0.30"
- Gap: 0.40"
- Name: max 92pt / min 64pt, 2 lines max, leading 1.20
- Phone: max 76pt / min 54pt
- Brokerage: max 56pt / min 40pt, single-line

QR card:
- QR: 10.60"
- Pad: 0.70"
- Outer: 12.00"
- Radius: 0.45"
- Border: 3pt, #E2E8F0

Footer:
- CTA: max 92pt / min 64pt
- URL: max 46pt / min 34pt

### Size: 36x24 (Landscape)
Trim: 36w × 24h  
Header: 3.80"  
Footer: 3.60"  
Accent: 0.10"

Header:
- Headshot: 2.60"
- Inset: 0.30"
- Gap: 0.35"
- Name: max 72pt / min 50pt, 2 lines max, leading 1.22
- Phone: max 62pt / min 44pt
- Brokerage: max 48pt / min 34pt, single-line

QR card:
- QR: 8.80"
- Pad: 0.65"
- Outer: 10.10"
- Radius: 0.40"
- Border: 3pt, #E2E8F0

Footer:
- CTA: max 72pt / min 50pt
- URL: max 40pt / min 30pt

---

# 4) Listing Sign Specs (Product-Level)

Listing sign supports 4 sizes: 12x18, 18x24, 24x36, 36x24.
(Define listing layouts separately in code; this section defines only product-level constraints.)

## 4.1 Listing Sign Content Hierarchy (Minimum)
- Address (or listing title) must be most prominent
- Price must be prominent if included
- QR must obey QR rules (quiet zone + contrast)
- Agent contact must never be smaller than URL text

## 4.2 Listing Sign Safe Margins + Bleed
Use Global rules unless specific print provider requires overrides.

---

# 5) Web Preview Rendering Constraints

The web preview must be:
- Fast (no hangs on large PDFs)
- Consistent enough to validate layout (no “preview mismatch” surprises)

## 5.1 Preview Target
- Target longest side: 1400–1800px (implementation may clamp)
- DPI must be dynamically scaled by page size and clamped to avoid huge rasterization.
- Preview must preserve aspect ratio; no cropping.

---

# 6) Validation Matrix (Must Match print_catalog)

| Product      | Allowed Sizes                              |
|-------------|---------------------------------------------|
| SmartSign    | 18x24, 24x36, 36x24                        |
| Listing Sign | 12x18, 18x24, 24x36, 36x24                 |

Any request outside matrix must be rejected.
