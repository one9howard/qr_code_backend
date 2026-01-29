"""Canonical Print Product Catalog & SKU Definitions

Single source of truth for:
- Available materials per product
- Strict size enforcement
- Stripe Lookup Key mapping
- Resolution of Price IDs via StripePriceResolver
"""
import logging
from services import stripe_price_resolver
from services.specs import PRODUCT_SIZE_MATRIX, SMARTSIGN_SIZES, LISTING_SIGN_SIZES

logger = logging.getLogger(__name__)

# --- Product Constants ---

# Valid Materials per Product
SMARTSIGN_MATERIALS = ('aluminum_040',)
SMART_RISER_MATERIALS = ('aluminum_040',)
LISTING_SIGN_MATERIALS = ('coroplast_4mm', 'aluminum_040')

# SIZES (Sourced from Canonical Specs)
SMART_SIGN_VALID_SIZES = tuple(SMARTSIGN_SIZES)
SMART_RISER_VALID_SIZES = ('6x24', '6x36') # Riser specs not in canonical matrix yet? Or just use hardcoded for now.

LISTING_SIGN_VALID_SIZES = {
    # Coroplast does not support 36x24
    'coroplast_4mm': ('12x18', '18x24', '24x36'),
    # Aluminum does not support 12x18
    'aluminum_040': ('18x24', '24x36', '36x24')
}

SMART_SIGN_LAYOUTS = (
    'smart_v1_photo_banner',
    'smart_v1_minimal',
    'smart_v1_agent_brand'
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
      Listing Sign: listing_sign_{material_short}_{size}  (WAIT - User spec says 'listing_sign_coroplast_18x24')
    
    User Schema:
      SmartSign (Alum): smart_sign_print_18x24
      SmartRiser (Alum): smart_riser_6x24
      Listing (Coro): listing_sign_coroplast_18x24
      Listing (Alum): listing_sign_aluminum_18x24
    """
    if print_product == 'smart_sign':
        # Material is always aluminum, not in key
        return f"smart_sign_print_{print_size}"
        
    elif print_product == 'smart_riser':
        # Material is always aluminum, not in key
        return f"smart_riser_{print_size}"
        
    elif print_product == 'listing_sign':
        if not material:
            raise ValueError("Material required for listing sign key")
        
        # Mappings for material part of key
        # User defined: listing_sign_coroplast_12x18 -> 'coroplast'
        # User defined: listing_sign_aluminum_18x24 -> 'aluminum'
        mat_key = 'coroplast' if 'coroplast' in material else 'aluminum'
        return f"listing_sign_{mat_key}_{print_size}"
        
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
            
    elif print_product == 'listing_sign':
        if material not in LISTING_SIGN_MATERIALS:
             return False, "invalid_material"
        
        # Dependent sizing
        allowed = LISTING_SIGN_VALID_SIZES.get(material, ())
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
        
    # Listing Signs
    for mat in LISTING_SIGN_MATERIALS:
        sizes = LISTING_SIGN_VALID_SIZES.get(mat, [])
        for size in sizes:
            keys.append(get_lookup_key('listing_sign', size, mat))
            
    return keys

# --- Validation Helpers ---

def validate_layout(print_product, layout_id):
    if print_product == 'smart_sign':
        if layout_id not in SMART_SIGN_LAYOUTS:
            return False, f"Invalid SmartSign layout: {layout_id}"
        return True, ""
    elif print_product == 'listing_sign':
        if not layout_id:
            return False, "Layout ID required"
        return True, ""
    elif print_product == 'smart_riser':
        # Risers might not have layouts yet? Assuming generic or none required.
        # Minimal for now:
        return True, ""
    return False, f"Unknown print product: {print_product}"
