import urllib.parse
from typing import Optional

def normalize_https_url(raw_url: str) -> Optional[str]:
    """
    Validates and normalizes a URL.
    - Must be HTTPS.
    - Must have a network location (host).
    - Max length 2048.
    - Rejects whitespace-only or empty strings.
    - reject javascript:, data:, etc (implicit via https requirement)
    
    Returns:
        Normalized URL string (whitespace stripped) or None if invalid.
    """
    if not raw_url or not raw_url.strip():
        return None
    
    url = raw_url.strip()
    
    if len(url) > 2048:
        return None
        
    try:
        parsed = urllib.parse.urlparse(url)
        
        # Must have scheme https
        if parsed.scheme.lower() != 'https':
            return None
            
        # Must have netloc (host)
        if not parsed.netloc:
            return None
            
        return url
    except Exception:
        return None
