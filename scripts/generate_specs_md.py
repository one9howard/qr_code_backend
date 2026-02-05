# scripts/generate_specs_md.py
from __future__ import annotations

import json
import sys
from pathlib import Path

# Fix import path for running from repo root
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from typing import Any, Dict, List

from services.specs import (
    PRODUCT_SIZE_MATRIX,
    GLOBAL_PRINT_RULES,
    SMARTSIGN_LAYOUT_IDS,
    SMARTSIGN_V1_MINIMAL_SPECS,
    LISTING_SIGN_CONSTRAINTS: YARD_SIGN_CONSTRAINTS,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = REPO_ROOT / "SPECS.md"

BEGIN = "<!-- BEGIN AUTO-GENERATED SPECS (DO NOT EDIT) -->"
END = "<!-- END AUTO-GENERATED SPECS (DO NOT EDIT) -->"


def md_table(rows: List[List[str]]) -> str:
    """Render a simple Markdown table. rows[0] is header."""
    if not rows:
        return ""
    header = rows[0]
    body = rows[1:]
    out: List[str] = []
    out.append("| " + " | ".join(header) + " |")
    out.append("| " + " | ".join(["---"] * len(header)) + " |")
    for r in body:
        out.append("| " + " | ".join(r) + " |")
    return "\n".join(out)


def dump_smartsign_v1_minimal(spec: Dict[str, Any]) -> str:
    """Render SmartSign smart_v1_minimal per-size block."""
    sizes: Dict[str, Any] = spec["sizes"]

    def size_block(size_key: str) -> str:
        s = sizes[size_key]
        header = s["header"]
        qr = s["qr"]
        fonts = s["fonts"]
        leading = s["leading"]
        gaps = s["gaps_in"]
        defaults = s.get("defaults", {})

        return f"""### Size: {size_key}
- Header height: **{s['header_h_in']}"**
- Footer height: **{s['footer_h_in']}"**
- Accent rule height: **{s['accent_rule_h_in']}"** (optional)

**Header**
- Headshot: **{header['headshot_in']}"**
- Headshot inset: **{header['headshot_inset_in']}"**
- Gap headshot→text: **{header['headshot_gap_in']}"**

**Fonts (start/min pt)**
- Name: **{fonts['name'][0]}/{fonts['name'][1]}** (2 lines max)
- Phone: **{fonts['phone'][0]}/{fonts['phone'][1]}** (single-line)
- Brokerage: **{fonts['brokerage'][0]}/{fonts['brokerage'][1]}** (single-line, ellipsis)
- CTA: **{fonts['cta'][0]}/{fonts['cta'][1]}**
- URL: **{fonts['url'][0]}/{fonts['url'][1]}**

**Leading**
- Name: **{leading['name']}**
- Phone: **{leading['phone']}**
- CTA: **{leading['cta']}**
- URL: **{leading['url']}**

**Gaps (inches)**
- Name→Phone: **{gaps['name_phone']}"**
- CTA→URL: **{gaps['cta_url']}"**
- Header pad: **{gaps['header_pad']}"**
- Footer pad: **{gaps['footer_pad']}"**
- Brokerage→Name gap: **{gaps['brokerage_name_gap']}"**

**QR card**
- QR size: **{qr['qr_size_in']}"**
- Card padding: **{qr['card_pad_in']}"**
- Card radius: **{qr['card_radius_in']}"**
- Card border: **{qr['card_border_pt']}pt**, `{qr['card_border_hex']}`

**Defaults**
- CTA text: `{defaults.get('cta_text', '')}`
"""

    blocks: List[str] = []
    for k in ("18x24", "24x36", "36x24"):
        if k in sizes:
            blocks.append(size_block(k))
    return "\n".join(blocks)


def generate_specs_md() -> str:
    bleed = GLOBAL_PRINT_RULES["bleed_in"]
    safe = GLOBAL_PRINT_RULES["safe_margin_in"]
    qr_rules = GLOBAL_PRINT_RULES["qr_rules"]
    fit_policy = GLOBAL_PRINT_RULES["text_fit_policy"]

    sizes_table = md_table([
        ["Product", "Allowed Sizes"],
        ["SmartSign", ", ".join(PRODUCT_SIZE_MATRIX["smart_sign"])],
        ["Yard Sign", ", ".join(PRODUCT_SIZE_MATRIX["yard_sign"])],
    ])

    safe_table = md_table([
        ["Size", "Safe margin (in)"],
        ["12x18", str(safe["12x18"])],
        ["18x24", str(safe["18x24"])],
        ["24x36", str(safe["24x36"])],
        ["36x24", str(safe["36x24"])],
    ])

    signature_pointer = {
        "specs_signature_version": 1,
        "source": "services/specs.py:SPECS_SIGNATURE",
    }
    sig_block = json.dumps(signature_pointer, indent=2, sort_keys=True)

    minimal_block = dump_smartsign_v1_minimal(SMARTSIGN_V1_MINIMAL_SPECS)

    return f"""# SPECS.md — Print + Layout Specifications (Single Source of Truth)

This file is **AUTO-GENERATED** from `services/specs.py`.

Do not hand-edit the generated content. Instead:
1) edit `services/specs.py`
2) run:
```bash
python scripts/generate_specs_md.py
```
commit the updated SPECS.md

{BEGIN}

1) Validation Matrix (Must Match Code)
{sizes_table}

2) Global Print Rules
Units: 1 inch = 72 pt

Bleed (all sides): {bleed}"

Safe margins (from trim edge inward):

{safe_table}

QR Rules (Scan Reliability)
Minimum quiet zone: {qr_rules['min_quiet_zone_in']}"

White card required on dark backgrounds: {qr_rules['require_white_card_on_dark_bg']}

QR rotation allowed: {not qr_rules['no_rotation']} (must be False)

Text Fit Policy
No overlaps allowed: {fit_policy['no_overlap']}

Priority (highest first): {", ".join(fit_policy["priority"])}

Overflow order: {", ".join(fit_policy["overflow_order"])}

3) SmartSign
Supported Layout IDs
{chr(10).join(f"- {lid}" for lid in SMARTSIGN_LAYOUT_IDS)}

smart_v1_minimal (Agent-First Minimal)
Background: {SMARTSIGN_V1_MINIMAL_SPECS["background"]}

Email enabled by default: {SMARTSIGN_V1_MINIMAL_SPECS["email_default_enabled"]}

Accent rule default: {SMARTSIGN_V1_MINIMAL_SPECS["accent_rule_default_hex"]}

{minimal_block}

4) Yard Sign (Product Constraints)
Supported sizes: {", ".join(YARD_SIGN_CONSTRAINTS["sizes"])}

Content hierarchy: {", ".join(YARD_SIGN_CONSTRAINTS["content_hierarchy"])}

Rule: {YARD_SIGN_CONSTRAINTS["agent_contact_min_readability_rule"]}

Appendix: Machine-Readable Signature (DO NOT EDIT BY HAND)
{sig_block}
{END}
"""

def main() -> int:
    md = generate_specs_md().replace("\r\n", "\n")
    OUT_PATH.write_text(md, encoding="utf-8", newline="\n")
    print(f"Wrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
