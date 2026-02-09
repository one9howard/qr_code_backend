from reportlab.lib.units import inch

# -----------------------------------------------------------------------------
# GLOBAL CONSTANTS
# -----------------------------------------------------------------------------
SAFE_MARGIN = 0.5 * inch
BLEED = 0.125 * inch

# -----------------------------------------------------------------------------
# TYPE SCALES (Points)
# -----------------------------------------------------------------------------
# Standard Modern
TYPE_SCALE_MODERN = {
    'address': {'max': 140, 'min': 48},
    'features': {'max': 42, 'min': 24},
    'price': {'max': 60, 'min': 36},
    'cta': {'max': 48, 'min': 24},
    'agent_name': {'max': 48, 'min': 24},
    'agent_sub': {'max': 32, 'min': 18},
}

# Serif Premium
TYPE_SCALE_SERIF = {
    'status': {'max': 120, 'min': 60},
    'address': {'max': 130, 'min': 50},
    'phone': {'max': 150, 'min': 60},
    'agent_name': {'max': 60, 'min': 30},
    'cta': {'max': 40, 'min': 20},
}

# -----------------------------------------------------------------------------
# GRID / SPACING
# -----------------------------------------------------------------------------
SPACING = {
    'xs': 0.1 * inch,
    'sm': 0.25 * inch,
    'md': 0.5 * inch,
    'lg': 1.0 * inch,
    'xl': 2.0 * inch,
}

# -----------------------------------------------------------------------------
# QR CONSTANTS
# -----------------------------------------------------------------------------
QR_MIN_SIZE = 3.0 * inch  # Minimum physical size for reliability
QR_QUIET_ZONE_FACTOR = 1.2  # 20% breathing room around QR code

# -----------------------------------------------------------------------------
# COMPOSITION HELPERS
# -----------------------------------------------------------------------------
def get_safe_rect(width, height):
    """Returns (x, y, w, h) of safe area."""
    return (
        SAFE_MARGIN,
        SAFE_MARGIN,
        width - (2 * SAFE_MARGIN),
        height - (2 * SAFE_MARGIN)
    )
