"""
Canonical QR Code Uniqueness Helper

Ensures QR codes are unique across ALL namespaces:
- sign_assets.code
- properties.qr_code
- qr_variants.code

CRITICAL: No other file should implement its own uniqueness logic.
"""
import secrets
from database import get_db


# URL-safe alphabet for code generation (uppercase alphanumeric, no confusing chars)
DEFAULT_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # No 0/O, 1/I/L


def is_code_taken(db, code: str) -> bool:
    """
    Check if a code exists in any QR namespace.
    
    Args:
        db: Database connection
        code: The code to check
        
    Returns:
        True if code exists in sign_assets, properties, or qr_variants
    """
    # Check sign_assets
    if db.execute("SELECT 1 FROM sign_assets WHERE code = %s", (code,)).fetchone():
        return True
    
    # Check properties
    if db.execute("SELECT 1 FROM properties WHERE qr_code = %s", (code,)).fetchone():
        return True
    
    # Check qr_variants
    if db.execute("SELECT 1 FROM qr_variants WHERE code = %s", (code,)).fetchone():
        return True
    
    return False


def generate_unique_code(
    db=None,
    *,
    length: int = 12,
    alphabet: str | None = None,
    max_tries: int = 1000,
    _candidate_fn=None  # For testing: allows injecting deterministic candidates
) -> str:
    """
    Generate a unique code that doesn't exist in any QR namespace.
    
    Args:
        db: Database connection. If None, get_db() is called.
        length: Length of the code (default 12)
        alphabet: Character set for code generation (default: URL-safe uppercase alnum)
        max_tries: Maximum attempts before raising (should never be reached)
        _candidate_fn: Optional test hook - callable that returns candidate codes
        
    Returns:
        A unique code string
        
    Raises:
        RuntimeError: If max_tries exceeded (should never happen in practice)
    """
    if db is None:
        db = get_db()
    
    if alphabet is None:
        alphabet = DEFAULT_ALPHABET
    
    for attempt in range(max_tries):
        # Generate candidate
        if _candidate_fn:
            code = _candidate_fn(attempt)
        else:
            # Use secrets for cryptographic randomness
            code = ''.join(secrets.choice(alphabet) for _ in range(length))
        
        # Check uniqueness
        if not is_code_taken(db, code):
            return code
    
    raise RuntimeError(f"Failed to generate unique code after {max_tries} attempts")
