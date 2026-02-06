# services/specs.py
"""
Canonical, machine-enforced specifications.

SPECS.md is human-readable canonical spec.
This module mirrors it exactly and exposes a stable signature for sync checks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

INCH = 72.0

# ---- 1) Product size matrices (Reality A) ----

SMARTSIGN_SIZES: List[str] = ["18x24", "24x36", "36x24"]  # purchasable
YARD_SIGN_SIZES: List[str] = ["12x18", "18x24", "24x36", "36x24"]
SMART_RISER_SIZES: List[str] = ["6x24", "6x36"] # purchasable

PRODUCT_SIZE_MATRIX: Dict[str, List[str]] = {
    "smart_sign": SMARTSIGN_SIZES,
    "yard_sign": YARD_SIGN_SIZES,
    "smart_riser": SMART_RISER_SIZES,
}

# ---- 2) Global rules ----

GLOBAL_PRINT_RULES: Dict[str, Any] = {
    "bleed_in": 0.125,
    "safe_margin_in": {
        "12x18": 0.50,
        "18x24": 0.50,
        "24x36": 0.50,
        "36x24": 0.60,
        "6x24": 0.25,
        "6x36": 0.25,
    },
    "qr_rules": {
        "min_quiet_zone_in": 0.25,  # minimum padding around QR modules
        "require_white_card_on_dark_bg": True,
        "no_rotation": True,
    },
    "text_fit_policy": {
        "no_overlap": True,
        "priority": ["agent_name", "phone", "cta", "url", "brokerage", "email"],
        "overflow_order": ["shrink_to_min", "ellipsis", "drop_lowest_priority"],
    },
}

# ---- 3) SmartSign layout IDs ----

SMARTSIGN_LAYOUT_IDS: List[str] = [
    "smart_v1_photo_banner",
    "smart_v1_minimal",      # Agent-First Minimal (Variant A)
    "smart_v1_agent_brand",
    "smart_v2_vertical_banner",  # Premium Vertical Banner
    "smart_v2_modern_round",     # Modern Round
]

# ---- 4) SmartSign: smart_v1_minimal (Variant A) ----
# All inches are trim-space measurements. Convert in generator with INCH.
# Font tuples are (start_pt, min_pt).

SMARTSIGN_V1_MINIMAL_SPECS: Dict[str, Any] = {
    "layout_id": "smart_v1_minimal",
    "background": "white",
    "accent_rule_default_hex": "#007AFF",
    "email_default_enabled": False,

    # Per-size specs
    "sizes": {
        "18x24": {
            "header_h_in": 3.40,
            "footer_h_in": 3.10,
            "accent_rule_h_in": 0.10,

            "header": {
                "headshot_in": 2.20,
                "headshot_inset_in": 0.25,
                "headshot_gap_in": 0.30,
            },
            "qr": {
                "qr_size_in": 7.20,
                "card_pad_in": 0.55,
                "card_radius_in": 0.35,
                "card_border_pt": 2,
                "card_border_hex": "#E2E8F0",
            },
            "fonts": {
                "name": (64, 44),
                "phone": (52, 38),
                "brokerage": (38, 28),  # single-line only
                "cta": (64, 44),
                "url": (34, 26),
            },
            "leading": {
                "name": 1.22,
                "phone": 1.15,
                "cta": 1.18,
                "url": 1.10,
            },
            "gaps_in": {
                "name_phone": 0.12,
                "cta_url": 0.10,
                "header_pad": 0.15,
                "footer_pad": 0.15,
                "brokerage_name_gap": 0.25,
            },
            "defaults": {
                "cta_text": "Price + Photos + 3D Tour",
            },
        },

        "24x36": {
            "header_h_in": 4.90,
            "footer_h_in": 4.40,
            "accent_rule_h_in": 0.12,

            "header": {
                "headshot_in": 3.10,
                "headshot_inset_in": 0.30,
                "headshot_gap_in": 0.40,
            },
            "qr": {
                "qr_size_in": 10.60,
                "card_pad_in": 0.70,
                "card_radius_in": 0.45,
                "card_border_pt": 3,
                "card_border_hex": "#E2E8F0",
            },
            "fonts": {
                "name": (92, 64),
                "phone": (76, 54),
                "brokerage": (56, 40),
                "cta": (92, 64),
                "url": (46, 34),
            },
            "leading": {
                "name": 1.20,
                "phone": 1.15,
                "cta": 1.18,
                "url": 1.10,
            },
            "gaps_in": {
                "name_phone": 0.14,
                "cta_url": 0.12,
                "header_pad": 0.18,
                "footer_pad": 0.18,
                "brokerage_name_gap": 0.30,
            },
            "defaults": {
                "cta_text": "Price + Photos + 3D Tour",
            },
        },

        "36x24": {
            "header_h_in": 3.80,
            "footer_h_in": 3.60,
            "accent_rule_h_in": 0.10,

            "header": {
                "headshot_in": 2.60,
                "headshot_inset_in": 0.30,
                "headshot_gap_in": 0.35,
            },
            "qr": {
                "qr_size_in": 8.80,
                "card_pad_in": 0.65,
                "card_radius_in": 0.40,
                "card_border_pt": 3,
                "card_border_hex": "#E2E8F0",
            },
            "fonts": {
                "name": (72, 50),
                "phone": (62, 44),
                "brokerage": (48, 34),
                "cta": (72, 50),
                "url": (40, 30),
            },
            "leading": {
                "name": 1.22,
                "phone": 1.15,
                "cta": 1.18,
                "url": 1.10,
            },
            "gaps_in": {
                "name_phone": 0.12,
                "cta_url": 0.10,
                "header_pad": 0.16,
                "footer_pad": 0.16,
                "brokerage_name_gap": 0.28,
            },
            "defaults": {
                "cta_text": "Price + Photos + 3D Tour",
            },
        },
    },
}

# ---- 5) Yard Sign: product-level constraints only (layout-specific specs may live elsewhere) ----

YARD_SIGN_CONSTRAINTS: Dict[str, Any] = {
    "product": "yard_sign",
    "sizes": YARD_SIGN_SIZES,
    "content_hierarchy": [
        "address_or_title",
        "price_if_present",
        "qr",
        "agent_contact",
    ],
    "agent_contact_min_readability_rule": "Agent contact must not be smaller than URL text.",
}

# ---- 6) Signature used by sync checks ----

def _signature() -> Dict[str, Any]:
    # Keep this intentionally small: only values that must never drift.
    return {
        "version": 1,
        "product_size_matrix": PRODUCT_SIZE_MATRIX,
        "global_print_rules": {
            "bleed_in": GLOBAL_PRINT_RULES["bleed_in"],
            "safe_margin_in": GLOBAL_PRINT_RULES["safe_margin_in"],
            "qr_rules": GLOBAL_PRINT_RULES["qr_rules"],
            "text_fit_policy": GLOBAL_PRINT_RULES["text_fit_policy"],
        },
        "smartsign_layout_ids": SMARTSIGN_LAYOUT_IDS,
        "smartsign_v1_minimal": SMARTSIGN_V1_MINIMAL_SPECS,
        "yard_sign_sizes": YARD_SIGN_SIZES,
    }

SPECS_SIGNATURE: Dict[str, Any] = _signature()
