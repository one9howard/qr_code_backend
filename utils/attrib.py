"""
Attribution Token Utilities

Provides secure, signed tokens for SmartSign → Lead attribution.
Tokens are HMAC-signed to prevent forgery.

Usage:
    from utils.attrib import make_attrib_token, verify_attrib_token
    
    # In /r/<code> route:
    token = make_attrib_token(asset_id, int(time.time()), app.config['SECRET_KEY'])
    response.set_cookie('smart_attrib', token, ...)
    
    # In lead submit:
    asset_id = verify_attrib_token(token, SECRET_KEY, max_age_seconds=7*24*3600)
    if asset_id:
        lead.sign_asset_id = asset_id
"""
import hmac
import hashlib
import time
from typing import Optional


def make_attrib_token(asset_id: int, issued_at: int, secret: str) -> str:
    """
    Create a signed attribution token.
    
    Token format: {asset_id}.{issued_at}.{signature}
    Signature is HMAC-SHA256 of "{asset_id}.{issued_at}" using secret.
    
    Args:
        asset_id: SmartSign asset ID
        issued_at: Unix timestamp when token was created
        secret: App secret key for signing
        
    Returns:
        URL-safe signed token string
    """
    base = f"{asset_id}.{issued_at}"
    sig = hmac.new(
        secret.encode('utf-8'),
        base.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()[:32]  # Truncate to 32 chars for URL brevity
    
    return f"{base}.{sig}"


def verify_attrib_token(token: str, secret: str, max_age_seconds: int) -> Optional[int]:
    """
    Verify a signed attribution token.
    
    Args:
        token: The token string from cookie
        secret: App secret key for verification
        max_age_seconds: Maximum token age in seconds (e.g., 7 days = 604800)
        
    Returns:
        asset_id if valid and not expired, None otherwise
    """
    if not token or not secret:
        return None
    
    try:
        parts = token.split('.')
        if len(parts) != 3:
            return None
        
        asset_id_str, issued_at_str, provided_sig = parts
        
        # Parse values
        asset_id = int(asset_id_str)
        issued_at = int(issued_at_str)
        
        # Check expiration
        now = int(time.time())
        if now - issued_at > max_age_seconds:
            return None
        
        # Recompute signature
        base = f"{asset_id}.{issued_at}"
        expected_sig = hmac.new(
            secret.encode('utf-8'),
            base.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()[:32]
        
        # Constant-time comparison to prevent timing attacks
        if not hmac.compare_digest(expected_sig, provided_sig):
            return None
        
        return asset_id
        
    except (ValueError, TypeError, IndexError):
        return None
