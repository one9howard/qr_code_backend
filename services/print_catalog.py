"""Canonical Print Product Catalog & SKU Definitions

Single source of truth for:
- Available materials per product
- Strict size enforcement
- Stripe Lookup Key mapping
- Resolution of Price IDs via StripePriceResolver
"""
import logging
import re
from services import stripe_price_resolver
from services.specs import PRODUCT_SIZE_MATRIX, SMARTSIGN_SIZES, YARD_SIGN_SIZES, SMART_RISER_SIZES, SMARTSIGN_LAYOUT_IDS

logger = logging.getLogger(__name__)

# --- Product Constants ---

# Valid Materials per Product
SMARTSIGN_MATERIALS = ('aluminum_040',)
SMART_RISER_MATERIALS = ('aluminum_040',)
YARD_SIGN_MATERIALS = ('coroplast_4mm', 'aluminum_040')

# SIZES (Sourced from Canonical Specs)
SMART_SIGN_VALID_SIZES = tuple(SMARTSIGN_SIZES)
SMART_RISER_VALID_SIZES = tuple(SMART_RISER_SIZES)

YARD_SIGN_VALID_SIZES = {
    # Coroplast does not support 36x24
    'coroplast_4mm': ('12x18', '18x24', '24x36'),
    # Aluminum does not support 12x18
    'aluminum_040': ('18x24', '24x36', '36x24')
}

SMART_SIGN_LAYOUTS = tuple(SMARTSIGN_LAYOUT_IDS)

# Layout display metadata (used by UI). This is intentionally optional:
# If a layout ID is added to SMARTSIGN_LAYOUT_IDS but missing here, the UI will still show it
# with a reasonable fallback name/description to avoid drift.
SMARTSIGN_LAYOUT_META = {
    "smart_v1_photo_banner": {
        "name": "Photo Banner",
        "desc": "Professional bottom banner with headshot.",
        "tier": "Standard",
    },
    "smart_v1_minimal": {
        "name": "Modern Minimal",
        "desc": "Clean white, focus on QR code.",
        "tier": "Standard",
    },
    "smart_v1_agent_brand": {
        "name": "Agent Brand",
        "desc": "Logo-centric with dark footer.",
        "tier": "Standard",
    },
    "smart_v2_vertical_banner": {
        "name": "Vertical Banner",
        "desc": "Script typography, side status rail.",
        "tier": "Premium",
    },
    "smart_v2_modern_round": {
        "name": "Modern Round",
        "desc": "Circular aesthetic, friendly & bold.",
        "tier": "Premium",
    },
    "smart_v2_modern_split": {
        "name": "Modern Split",
        "desc": "Clean split grid, big QR panel.",
        "tier": "Premium",
    },
    "smart_v2_elegant_serif": {
        "name": "Elegant Serif",
        "desc": "Gold border, classic typography.",
        "tier": "Premium",
    },
    "smart_v2_bold_frame": {
        "name": "Bold Frame",
        "desc": "Heavy frame, high-contrast CTA.",
        "tier": "Premium",
    },
}

def _layout_id_to_title(layout_id: str) -> str:
    # Fallback: strip product prefix and version markers
    s = (layout_id or "").strip()
    s = re.sub(r"^smart_", "", s)
    s = re.sub(r"^v\d+_", "", s)
    return " ".join([w.capitalize() for w in s.split("_") if w])

def get_smartsign_layout_options():
    """Return SmartSign layout options for UI, driven by canonical specs.

    Contract:
    - IDs come from services.specs.SMARTSIGN_LAYOUT_IDS (single source of truth).
    - Optional display metadata comes from SMARTSIGN_LAYOUT_META.
    - If metadata is missing, we still return a usable option to prevent template drift.
    """
    opts = []
    for layout_id in SMARTSIGN_LAYOUT_IDS:
        meta = SMARTSIGN_LAYOUT_META.get(layout_id, {})
        name = meta.get("name") or _layout_id_to_title(layout_id) or layout_id
        desc = meta.get("desc") or ""
        tier = meta.get("tier") or ("Premium" if layout_id.startswith("smart_v2_") else "Standard")
        opts.append({
            "id": layout_id,
            "name": name,
            "desc": desc,
            "tier": tier,
            "is_premium": (tier.lower() == "premium"),
        })
    return opts
YARD_SIGN_LAYOUTS = (
    'yard_standard',
    'yard_modern_round',
    'yard_phone_qr_premium',
    'yard_address_qr_premium',
    # Legacy aliases (accepted for backward compatibility)
    'listing_standard',
    'listing_modern_round',
    'listing_v2_phone_qr_premium',
    'listing_v2_address_qr_premium',
)

# Strict Color Palette (ID -> Hex)
BANNER_COLOR_PALETTE = {
    'blue': '#0077ff',
    'navy': '#0f172a',
    'black': '#000000',
    'white': '#ffffff',
    'red': '#ef4444',
    'green': '#22c55e',
    'orange': '#f97316',
    'gray': '#64748b'
}

# --- Lookup Key Logic ---

def get_lookup_key(print_product: str, print_size: str, material: str = None) -> str:
    """
    Generate the canonical Stripe Lookup Key for the product combo.
    Format:
      SmartSign: smart_sign_print_{size}
      SmartRiser: smart_riser_{size}
      Yard Sign: yard_sign_{material_short}_{size}  (WAIT - User spec says 'yard_sign_coroplast_18x24')
    
    User Schema:
      SmartSign (Alum): smart_sign_print_18x24
      SmartRiser (Alum): smart_riser_6x24
      Yard Sign (Coro): yard_sign_coroplast_18x24
      Yard Sign (Alum): yard_sign_aluminum_18x24

    Returns:
        str: Lookup key (e.g. "smart_sign_18x24", "yard_sign_coroplast_18x24")
    """
    if print_product == 'smart_sign':
        # Smart signs imply material based on premium nature (mock logic)
        # We just need size.
        return f"smart_sign_print_{print_size}"
        
    elif print_product == 'smart_riser':
        # Material is always aluminum, not in key
        return f"smart_riser_{print_size}"
        
    elif print_product == 'yard_sign':
        # "listing_sign" logic requires material
        if not material:
            raise ValueError("Material required for yard_sign lookup")
        
        # Map nice names to key fragments
        # User defined: yard_sign_coroplast_12x18 -> 'coroplast'
        # User defined: yard_sign_aluminum_18x24 -> 'aluminum'
        mat_key = 'coroplast' if 'coroplast' in material else 'aluminum'
        return f"yard_sign_{mat_key}_{print_size}"
        
    raise ValueError(f"Unknown product for lookup key: {print_product}")


def validate_sku_strict(print_product, print_size, material):
    """
    Strict validation of product/size/material combos.
    Returns (ok: bool, reason: str).
    """
    if not print_product or not print_size:
        return False, "Missing product or size"
    
    # 1. Product Rules
    if print_product == 'smart_sign':
        if material not in SMARTSIGN_MATERIALS:
             return False, "invalid_material"
        if print_size not in SMART_SIGN_VALID_SIZES:
             return False, "invalid_size"
             
    elif print_product == 'smart_riser':
        if material not in SMART_RISER_MATERIALS:
             return False, "invalid_material"
        if print_size not in SMART_RISER_VALID_SIZES:
            return False, "invalid_size"
            
    elif print_product == 'yard_sign':
        if material not in YARD_SIGN_MATERIALS:
             return False, "invalid_material"
        
        # Dependent sizing
        allowed = YARD_SIGN_VALID_SIZES.get(material, ())
        if print_size not in allowed:
            return False, f"invalid_size_for_material"
            
    else:
        return False, "invalid_product"
        
    return True, ""


# Backward-compatible alias
validate_sku = validate_sku_strict


def get_price_id(print_product, print_size, material):
    """
    Get the Stripe Price ID using the Resolver.
    Validates SKU first.
    """
    ok, reason = validate_sku_strict(print_product, print_size, material)
    if not ok:
        raise ValueError(f"Invalid SKU: {reason}")
    
    key = get_lookup_key(print_product, print_size, material)
    
    # Resolve (will use cache)
    return stripe_price_resolver.resolve_price_id(key)


def get_all_required_lookup_keys() -> list[str]:
    """
    Helper to generate list of all lookup keys for warm_cache.
    Iterates all valid combos.
    """
    keys = []
    
    # Smart Signs
    for size in SMART_SIGN_VALID_SIZES:
        keys.append(get_lookup_key('smart_sign', size, 'aluminum_040'))
        
    # Smart Risers
    for size in SMART_RISER_VALID_SIZES:
        keys.append(get_lookup_key('smart_riser', size, 'aluminum_040'))
        
    # Yard Signs
    for mat in YARD_SIGN_MATERIALS:
        sizes = YARD_SIGN_VALID_SIZES.get(mat, [])
        for size in sizes:
            keys.append(get_lookup_key('yard_sign', size, mat))
            
    return keys

# --- Validation Helpers ---

def validate_layout(print_product, layout_id):
    if print_product == 'smart_sign':
        if layout_id not in SMART_SIGN_LAYOUTS:
            return False, f"Invalid SmartSign layout: {layout_id}"
        return True, ""
    elif print_product == 'yard_sign':
        if not layout_id:
            return False, "Layout ID required"
        if layout_id not in YARD_SIGN_LAYOUTS:
             return False, f"Invalid Yard Sign layout: {layout_id}"
        return True, ""
    elif print_product == 'smart_riser':
        # Risers might not have layouts yet? Assuming generic or none required.
        # Minimal for now:
        return True, ""
    return False, f"Unknown print product: {print_product}"
