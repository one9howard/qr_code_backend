# SPECS.md — Print + Layout Specifications (Single Source of Truth)

This file is **AUTO-GENERATED** from `services/specs.py`.

Do not hand-edit the generated content. Instead:
1) edit `services/specs.py`
2) run:
```bash
python scripts/generate_specs_md.py
```
commit the updated SPECS.md

<!-- BEGIN AUTO-GENERATED SPECS (DO NOT EDIT) -->

1) Validation Matrix (Must Match Code)
| Product | Allowed Sizes |
| --- | --- |
| SmartSign | 18x24, 24x36, 36x24 |
| Yard Sign | 12x18, 18x24, 24x36, 36x24 |

2) Global Print Rules
Units: 1 inch = 72 pt

Bleed (all sides): 0.125"

Safe margins (from trim edge inward):

| Size | Safe margin (in) |
| --- | --- |
| 12x18 | 0.5 |
| 18x24 | 0.5 |
| 24x36 | 0.5 |
| 36x24 | 0.6 |

QR Rules (Scan Reliability)
Minimum quiet zone: 0.25"

White card required on dark backgrounds: True

QR rotation allowed: False (must be False)

Text Fit Policy
No overlaps allowed: True

Priority (highest first): agent_name, phone, cta, url, brokerage, email

Overflow order: shrink_to_min, ellipsis, drop_lowest_priority

3) SmartSign
Supported Layout IDs
- smart_v1_photo_banner
- smart_v1_minimal
- smart_v1_agent_brand
- smart_v2_vertical_banner

smart_v1_minimal (Agent-First Minimal)
Background: white

Email enabled by default: False

Accent rule default: #007AFF

### Size: 18x24
- Header height: **3.4"**
- Footer height: **3.1"**
- Accent rule height: **0.1"** (optional)

**Header**
- Headshot: **2.2"**
- Headshot inset: **0.25"**
- Gap headshot→text: **0.3"**

**Fonts (start/min pt)**
- Name: **64/44** (2 lines max)
- Phone: **52/38** (single-line)
- Brokerage: **38/28** (single-line, ellipsis)
- CTA: **64/44**
- URL: **34/26**

**Leading**
- Name: **1.22**
- Phone: **1.15**
- CTA: **1.18**
- URL: **1.1**

**Gaps (inches)**
- Name→Phone: **0.12"**
- CTA→URL: **0.1"**
- Header pad: **0.15"**
- Footer pad: **0.15"**
- Brokerage→Name gap: **0.25"**

**QR card**
- QR size: **7.2"**
- Card padding: **0.55"**
- Card radius: **0.35"**
- Card border: **2pt**, `#E2E8F0`

**Defaults**
- CTA text: `Price + Photos + 3D Tour`

### Size: 24x36
- Header height: **4.9"**
- Footer height: **4.4"**
- Accent rule height: **0.12"** (optional)

**Header**
- Headshot: **3.1"**
- Headshot inset: **0.3"**
- Gap headshot→text: **0.4"**

**Fonts (start/min pt)**
- Name: **92/64** (2 lines max)
- Phone: **76/54** (single-line)
- Brokerage: **56/40** (single-line, ellipsis)
- CTA: **92/64**
- URL: **46/34**

**Leading**
- Name: **1.2**
- Phone: **1.15**
- CTA: **1.18**
- URL: **1.1**

**Gaps (inches)**
- Name→Phone: **0.14"**
- CTA→URL: **0.12"**
- Header pad: **0.18"**
- Footer pad: **0.18"**
- Brokerage→Name gap: **0.3"**

**QR card**
- QR size: **10.6"**
- Card padding: **0.7"**
- Card radius: **0.45"**
- Card border: **3pt**, `#E2E8F0`

**Defaults**
- CTA text: `Price + Photos + 3D Tour`

### Size: 36x24
- Header height: **3.8"**
- Footer height: **3.6"**
- Accent rule height: **0.1"** (optional)

**Header**
- Headshot: **2.6"**
- Headshot inset: **0.3"**
- Gap headshot→text: **0.35"**

**Fonts (start/min pt)**
- Name: **72/50** (2 lines max)
- Phone: **62/44** (single-line)
- Brokerage: **48/34** (single-line, ellipsis)
- CTA: **72/50**
- URL: **40/30**

**Leading**
- Name: **1.22**
- Phone: **1.15**
- CTA: **1.18**
- URL: **1.1**

**Gaps (inches)**
- Name→Phone: **0.12"**
- CTA→URL: **0.1"**
- Header pad: **0.16"**
- Footer pad: **0.16"**
- Brokerage→Name gap: **0.28"**

**QR card**
- QR size: **8.8"**
- Card padding: **0.65"**
- Card radius: **0.4"**
- Card border: **3pt**, `#E2E8F0`

**Defaults**
- CTA text: `Price + Photos + 3D Tour`


4) Yard Sign (Product Constraints)
Supported sizes: 12x18, 18x24, 24x36, 36x24

Content hierarchy: address_or_title, price_if_present, qr, agent_contact

Rule: Agent contact must not be smaller than URL text.

Appendix: Machine-Readable Signature (DO NOT EDIT BY HAND)
{
  "source": "services/specs.py:SPECS_SIGNATURE",
  "specs_signature_version": 1
}
<!-- END AUTO-GENERATED SPECS (DO NOT EDIT) -->
