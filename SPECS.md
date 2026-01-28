# SPECS.md — SmartSign Print Layout Specifications (Professional, Deterministic)
**Last updated:** 2026-01-28  
**Scope:** SmartSign PDF generation + previews + fulfillment outputs  
**Applies to:** `services/pdf_smartsign.py` (source-of-truth generator), and any other generator must match.

---

## 0) Non-negotiables

1) **Preview must match print**
- The same PDF generator used by fulfillment must be used for the web preview.
- No separate “preview-only” layout logic.

2) **Internal-only routing + printed fallback must be correct**
- Printed fallback URL MUST be `insite.co/r/<CODE>` (or `{BASE_DOMAIN}/r/<CODE}`).
- Never print `{BASE_DOMAIN}/<CODE>` (missing `/r/`).

3) **QR scan reliability**
- QR must be black on pure white.
- QR must have a white quiet zone (padding) around it.
- No gradients, glows, textures, or dark fills behind/near QR.
- No decorations within the QR quiet zone.

4) **Safe zone is sacred**
- All text must be inside the safe rect (trim inset by safe margin).
- If content doesn’t fit, it must shrink, wrap (max 2 lines where allowed), or ellipsize.
- Never overflow beyond safe margins.

5) **Deterministic, spec-driven**
- No “5% of width” heuristics.
- No string-length hacks (e.g., `len(name) > 20`).
- Use measured text widths (`canvas.stringWidth`) and measured block heights.

---

## 1) Supported sizes and orientation

Sizes are expressed as WIDTH×HEIGHT (inches). Orientation is- **Supported sizes and orientation**:
  - 18x24 (Portrait)
  - 24x36 (Portrait)
  - 36x24 (Landscape)

All measurements below are exact and must be converted using:
- `1 inch = 72 points`
- Use `reportlab.lib.units.inch`

---

## 2) Layout IDs

Layout selection is driven by `layout_id`:

- `smart_v1_photo_banner` — existing legacy/photo banner layout (do not change here)
- `smart_v1_minimal` — **Modern Minimal**
- `smart_v1_agent_brand` — **Agent Brand**

Dispatch rule:
- `smart_v1_photo_banner` → legacy renderer
- `smart_v1_agent_brand` → Agent Brand renderer
- otherwise → Modern Minimal renderer

---

## 3) Global print geometry

### 3.1 Bleed
- Bleed on all sides: **0.125"** (9 pt)

### 3.2 Safe margin (trim inset)
Safe margin differs per size:

| Size   | Safe margin (in) | Safe margin (pt) |
|--------|------------------:|-----------------:|
| 12x18  | 0.60"            | 43.2 pt          |
| 18x24  | 0.75"            | 54.0 pt          |
| 24x36  | 1.00"            | 72.0 pt          |
| 36x18  | 0.90"            | 64.8 pt          |
| 36x24  | 1.00"            | 72.0 pt          |

**Safe rect definition**
- Trim rect: `(0,0,width,height)` in points
- Safe rect: trim rect inset by safe margin on all sides  
  (NOT bleed inset — bleed is outside trim)

### 3.3 QR card styling (backing behind QR)
- Card fill: white `#ffffff`
- Card stroke: `#e2e8f0`
- Stroke width: **2 pt**
- Corner radius: **0.25"** (18 pt)
- **No shadows** (print-safe default)

### 3.4 Colors
- Primary text: `#0f172a`
- Secondary text: `#475569`
- Rule/border: `#e2e8f0`
- Agent Brand band background: `#0f172a`
- Accent: `banner_color_id` via `BANNER_COLOR_PALETTE`  
  - If accent resolves to white, use `#cbd5e1` for rule lines.

---

## 4) Text fitting rules (must implement)

All text must be measured and fit within a max width.

### 4.1 Single-line fit
Given `(text, font, start_size, min_size, max_width)`:
- Try `start_size`, decrement (or binary search) until it fits max_width.
- If still too wide at min_size: ellipsize to fit.
- Never allow overflow beyond max_width.

### 4.2 Two-line fit (for name/brokerage where allowed)
Given `(text, font, start_size, min_size, max_width, max_lines=2)`:
- Attempt one line first.
- If overflow, wrap into 2 lines (word-aware).
- Shrink to fit if needed.
- If still overflow at min_size: ellipsize the last line.

### 4.3 Block height must be returned
Multiline fitter must return:
- font size used
- lines rendered
- block height used (`line_count * size * leading_factor`)
This is required to compute vertical stacking without overlaps.

### 4.4 Allowed wrapping
- Agent name: max 2 lines
- Brokerage: max 2 lines
- Phone: 1 line only (shrink/ellipsize if needed)
- Email: 1 line only (shrink/omit if needed)
- CTA: 1 line (Minimal) / fixed 2 lines (Agent Brand)
- URL: 1 line only (shrink/ellipsize if needed)

---

## 5) Modern Minimal (smart_v1_minimal) — per-size specs

Modern Minimal structure:
- White background
- Thin top accent bar (accent color)
- Header band: 2-column grid:
  - Left: agent name + phone + optional email (stacked)
  - Right: brokerage (or logo), right-aligned
- Center QR zone
- Footer band: CTA line + URL line, centered

Header grid widths:
- Left column: 62%
- Column gap: 3%
- Right column: 35%

### 5.1 12x18
- Top accent bar: **0.45"**
- Header band height: **3.20"**
- Footer band height: **2.80"**
- QR size: **7.50"**
### 5.1 18x24
- Top accent bar: **0.55"**
- Header band: **4.00"**
- Footer band: **3.40"**
- QR size: **11.00"**
- QR padding: **0.55"**

Fonts:
- Agent name: **72 / 50**
- Phone: **96 / 68**
- Email: **30 / 22**
- Brokerage: **52 / 34**
- CTA: **72 / 54**
- URL: **28 / 22**

### 5.2 24x36
- Top bar: **0.70"**
- Header band: **5.60"**
- Footer band: **4.80"**
- QR size: **15.00"**
- QR padding: **0.75"**

Fonts:
- Name: **96 / 66**
- Phone: **120 / 88**
- Email: **40 / 28**
- Brokerage: **72 / 50**
- CTA: **96 / 72**
- URL: **34 / 26**

### 5.3 36x24 (landscape)
- Top bar: **0.70"**
- Header band: **4.20"**
- Footer band: **4.00"**
- QR size: **13.00"**
- QR padding: **0.70"**

Fonts:
- Name: **96 / 66**
- Phone: **120 / 88**
- Email: **36 / 26**
- Brokerage: **72 / 50**
- CTA: **96 / 72**
- URL: **34 / 26**

---

## 6) Agent Brand (smart_v1_agent_brand) — per-size specs

Agent Brand structure:
- White base
- Top brand band (navy) with accent rule
  - Left: headshot/logo circle (or monogram)
  - Center: agent name (max 2 lines)
  - Right: brokerage text/logo (max 2 lines)
- Center QR zone with white QR card
- Bottom brand footer band (navy) with accent rule
  - CTA in two lines:
    - Line 1: `SCAN` (white) + `FOR` (accent)
    - Line 2: `DETAILS` (accent)
  - URL below CTA, centered

### 6.1 18x24
- Top band: **4.50"**
- Footer band: **4.50"**
- QR size: **11.00"**
- QR padding: **0.55"**
- Logo/monogram diameter: **1.90"**

Fonts:
- Agent: **64 / 44**
- Brokerage: **56 / 38**
- “Scan Me”: **44 / 34**
- CTA1: **80 / 60**
- CTA2: **96 / 72**
- URL: **28 / 22**

### 6.2 24x36
- Top band: **6.40"**
- Footer band: **6.40"**
- QR size: **15.00"**
- QR padding: **0.75"**
- Logo/monogram diameter: **2.60"**

Fonts:
- Agent: **86 / 60**
- Brokerage: **76 / 54**
- “Scan Me”: **56 / 42**
- CTA1: **110 / 80**
- CTA2: **132 / 96**
- URL: **34 / 26**

### 6.3 36x24 (landscape)
- Top band: **5.00"**
- Footer band: **5.00"**
- QR size: **13.00"**
- QR padding: **0.70"**
- Logo diameter: **2.40"**

Fonts:
- Agent: **86 / 60** (allow shrink sooner if needed)
- Brokerage: **76 / 54**
- “Scan Me”: **56 / 42**
- CTA1: **110 / 80**
- CTA2: **132 / 96**
- URL: **34 / 26**

---

## 7) Photo Banner (smart_v1_photo_banner) — per-size specs

**Structure**:
- White base background.
- Top band (Accent/Navy) with:
  - Left: agent headshot circle (or logo)
  - Center-left: Agent Name (max 2 lines) + Phone (1 line) stack
  - Right: Brokerage logo/text (max 2 lines)
- Center QR zone with white QR card
- Bottom footer band (Accent/Navy):
  - CTA (1 line)
  - URL (1 line) - Safe-bottom anchored

**Note**: Since this layout shares "Banded" genetics with Agent Brand, we reuse similar band heights but adapt fonts for the denser header content.

### 7.1 18x24
- Top band: **4.50"**
- Footer band: **4.50"**
- Safe Margin: **0.75"**
- Headshot diameter: **1.90"**
- Fonts:
  - [Name]: **64 / 44** (Helvetica Bold, Left)
  - [Phone]: **48 / 36** (Helvetica Bold, Left, below name)
  - [Brokerage]: **56 / 38** (Helvetica Regular, Left, below phone)
  - [CTA]: **80 / 60** (Helvetica Bold, Footer)
  - [URL]: **28 / 22** (Helvetica Regular)

### 7.2 24x36
- Top band: **6.40"**
- Footer band: **6.40"**
- Safe Margin: **1.00"**
- Headshot diameter: **2.60"**
- Fonts:
  - [Name]: **86 / 60** (Helvetica Bold)
  - [Phone]: **64 / 48** (Helvetica Bold)
  - [Brokerage]: **76 / 54** (Helvetica Regular)
  - [CTA]: **110 / 80** (Helvetica Bold)
  - [URL]: **34 / 26** (Helvetica Regular)

### 7.3 36x24 (landscape)
- Top band: **5.00"**
- Footer band: **5.00"**
- Safe Margin: **1.00"**
- Headshot diameter: **2.40"**
- Fonts:
  - [Name]: **86 / 60** (Helvetica Bold)
  - [Phone]: **64 / 48** (Helvetica Bold)
  - [Brokerage]: **76 / 54** (Helvetica Regular)
  - [CTA]: **110 / 80**
  - [URL]: **34 / 26**


---

## 8) Worst-case fixtures (required test inputs)

Use these strings in verification scripts:

- Agent name:
  - `Alexandria Catherine Van Der Westhuizen`
- Brokerage:
  - `Sotheby’s International Realty – Northern California Peninsula`
- Email:
  - `alexandria.vanderwesthuizen.longemailaddress@gmail.com`
- Phone:
  - `(555) 555-5555`
- Code:
  - `ABCD1234`

Acceptance: no overlaps, no safe margin breaches, URL prints `/r/ABCD1234`.

---

## 9) Verification requirements (must be automated)

Create/maintain a script (recommended: `scripts/verify_smartsign_layouts.py`) that:

1) Generates PDFs for:
- all sizes × both layouts = 10 outputs
2) Renders each PDF to preview (webp) using the real preview pipeline
3) Extracts text block bounding boxes from the PDF (PyMuPDF recommended)
4) Asserts all text blocks are within the safe rect (tolerance ≤ 1 pt)
5) Prints a PASS/FAIL table and exits non-zero on any failure

Manual check is allowed as a supplement, not a replacement.


---
