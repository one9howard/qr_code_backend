# Order Status Constants
ORDER_STATUS_PENDING_PAYMENT = "pending_payment"
ORDER_STATUS_PAID = "paid"
ORDER_STATUS_PENDING_PRODUCTION = "pending_production"  # Legacy, use submitted_to_printer instead
ORDER_STATUS_SUBMITTED_TO_PRINTER = "submitted_to_printer"
ORDER_STATUS_PRINT_FAILED = "print_failed"
ORDER_STATUS_FULFILLED = "fulfilled"  # Reserved for future delivery confirmation

# Statuses that indicate payment has been received (for download/access gating)
PAID_STATUSES = frozenset({
    ORDER_STATUS_PAID,
    ORDER_STATUS_SUBMITTED_TO_PRINTER,
    ORDER_STATUS_FULFILLED,
    ORDER_STATUS_PRINT_FAILED,
})

# Sign Size Presets (inches to pixels for rendering)
SIGN_SIZES = {
    "12x18": {"width_in": 12, "height_in": 18, "dpi": 300},
    "18x24": {"width_in": 18, "height_in": 24, "dpi": 300},  # Default
    "24x36": {"width_in": 24, "height_in": 36, "dpi": 300},
    "36x24": {"width_in": 36, "height_in": 24, "dpi": 300},
}

DEFAULT_SIGN_SIZE = "18x24"

# Sign Color Palette
SIGN_COLORS = {
    "blue": {"hex": "#0077ff", "name": "Ocean Blue"},      # Default (Updated to Brand Blue)
    "green": {"hex": "#2EA043", "name": "Forest Green"},
    "red": {"hex": "#CF222E", "name": "Ruby Red"},
    "purple": {"hex": "#8250DF", "name": "Royal Purple"},
    "orange": {"hex": "#FB8500", "name": "Sunset Orange"},
    "teal": {"hex": "#0969DA", "name": "Sky Teal"},
}

DEFAULT_SIGN_COLOR = "#0077ff"

# Layout Version - Bump this when PDF/preview layout changes significantly
# Used for cache busting and filename versioning
LAYOUT_VERSION = 2

