"""
Canonical helpers for QR scan URLs.
Single source of truth for constructing redirect URLs.
Strictly enforce /r/<code> format.
"""

def property_scan_url(base_url: str, qr_code: str) -> str:
    """
    Generate canonical scan URL for a property QR code.
    Format: {base_url}/r/{qr_code}
    """
    if not qr_code:
        raise ValueError("qr_code is required for scan URL")
    
    clean_base = base_url.rstrip('/')
    return f"{clean_base}/r/{qr_code}"


def asset_scan_url(base_url: str, asset_code: str) -> str:
    """
    Generate canonical scan URL for a SmartSign asset code.
    Format: {base_url}/r/{asset_code}
    """
    if not asset_code:
        raise ValueError("asset_code is required for scan URL")
    
    clean_base = base_url.rstrip('/')
    return f"{clean_base}/r/{asset_code}"
