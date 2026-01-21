"""Canonical Print Product Catalog & SKU Definitions

Single source of truth for:
- Available materials and sides per product
- Valid layout IDs
- Color palettes
- Price mapping
"""
import os

# --- Constants ---

LISTING_SIGN_MATERIALS = ('coroplast_4mm', 'aluminum_040')
SMART_SIGN_MATERIALS = ('aluminum_040',)

SIDES = ('single', 'double')

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

# --- Helpers ---

def validate_sku(print_product, material, sides):
    """
    Validate that the combination of product, material, and sides is allowed.
    Returns (ok: bool, reason: str).
    """
    if sides not in SIDES:
        return False, f"Invalid sides: {sides}"
        
    if print_product == 'listing_sign':
        if material not in LISTING_SIGN_MATERIALS:
            return False, f"Invalid material for Listing Sign: {material}"
        return True, ""
        
    elif print_product == 'smart_sign':
        if material not in SMART_SIGN_MATERIALS:
            return False, f"Invalid material for SmartSign: {material}"
        return True, ""
        
    return False, f"Unknown print product: {print_product}"


def validate_layout(print_product, layout_id):
    """
    Validate layout ID for the given product.
    Returns (ok: bool, reason: str).
    """
    if print_product == 'smart_sign':
        if layout_id not in SMART_SIGN_LAYOUTS:
            return False, f"Invalid SmartSign layout: {layout_id}"
        return True, ""
        
    elif print_product == 'listing_sign':
        # Listing signs use existing flexible layout logic (e.g. 'classic_luxury', etc.)
        # For now, we assume any non-empty string is potentially valid, 
        # or we could strictly check against existing known layouts if desired.
        # But per instructions: "Listing: keep existing, but expose a list function..."
        if not layout_id:
            return False, "Layout ID required"
        return True, ""
        
    return False, f"Unknown print product: {print_product}"

def get_price_id(print_product, material, sides):
    """
    Get the Stripe Price ID for a valid SKU.
    Raises ValueError if SKU invalid or env var missing.
    NO secrets printed.
    """
    valid, reason = validate_sku(print_product, material, sides)
    if not valid:
        raise ValueError(f"Cannot get price for invalid SKU: {reason}")

    env_var = None
    
    if print_product == 'listing_sign':
        if material == 'coroplast_4mm' and sides == 'single':
            env_var = 'STRIPE_PRICE_LISTING_CORO_SINGLE'
        elif material == 'coroplast_4mm' and sides == 'double':
            env_var = 'STRIPE_PRICE_LISTING_CORO_DOUBLE'
        elif material == 'aluminum_040' and sides == 'single':
            env_var = 'STRIPE_PRICE_LISTING_ALUM_SINGLE'
        elif material == 'aluminum_040' and sides == 'double':
            env_var = 'STRIPE_PRICE_LISTING_ALUM_DOUBLE'
            
    elif print_product == 'smart_sign':
        # SmartSign is Aluminum only
        if material == 'aluminum_040' and sides == 'single':
            env_var = 'STRIPE_PRICE_SMART_ALUM_SINGLE'
        elif material == 'aluminum_040' and sides == 'double':
            env_var = 'STRIPE_PRICE_SMART_ALUM_DOUBLE'

    if not env_var:
        # Should be covered by validate_sku logic, but safe fallback
        raise ValueError(f"No price mapping for {print_product} {material} {sides}")

    price_id = os.environ.get(env_var)
    if not price_id:
        raise ValueError(f"Missing configuration: {env_var} is not set.")
        
    return price_id
