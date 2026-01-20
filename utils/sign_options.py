import re
import logging
from constants import SIGN_SIZES, DEFAULT_SIGN_SIZE

logger = logging.getLogger(__name__)

# Canonical list of sizes derived from constants
ALLOWED_SIGN_SIZES = set(SIGN_SIZES.keys())

# Known typo mappings
TYPO_FIXES = {
    "24x26": "24x36"
}

def normalize_sign_size(raw_size: str) -> str:
    """
    Normalize user/DB input into canonical sizes.
    Accepts common variants like 12x18, 12"x18", 12 X 18, 24x26 (typo) -> 24x36.
    
    Args:
        raw_size (str): The raw size string from input or database.
        
    Returns:
        str: A canonical size string (e.g., "18x24"). Returns DEFAULT_SIGN_SIZE if invalid.
    """
    if not raw_size:
        return DEFAULT_SIGN_SIZE

    # 1. Basic cleanup: lower, strip
    s = str(raw_size).lower().strip()
    
    # 2. Remove inches symbol ("), spaces
    s = s.replace('"', '').replace("'", "")
    
    # 3. Collapse multiple spaces
    s = re.sub(r'\s+', '', s)
    
    # 4. Standardize separator: replace '×' or '*' with 'x'
    s = s.replace('×', 'x').replace('*', 'x')
    
    # 5. Check typo fixes
    if s in TYPO_FIXES:
        logger.info(f"Corrected sign size typo: '{raw_size}' -> '{TYPO_FIXES[s]}'")
        s = TYPO_FIXES[s]
        
    # 6. Validate against allowed sizes
    if s in ALLOWED_SIGN_SIZES:
        return s
        
    # 7. Fallback
    logger.warning(f"Invalid sign size encountered: '{raw_size}' (normalized: '{s}'). Defaulting to {DEFAULT_SIGN_SIZE}.")
    return DEFAULT_SIGN_SIZE
