"""
Safe environment variable helper with sanitization support.
"""
import os
from typing import Optional


def get_env_str(
    name: str,
    default: Optional[str] = None,
    required: bool = False,
    strip: bool = True
) -> Optional[str]:
    """
    Safely read an environment variable with optional stripping.
    
    This is particularly important for secrets like STRIPE_WEBHOOK_SECRET
    where accidental whitespace can break signature verification.
    
    Args:
        name: Environment variable name
        default: Default value if not set or empty after strip
        required: If True, raise ValueError when missing/empty
        strip: If True, strip leading/trailing whitespace (default: True)
    
    Returns:
        The value (stripped if requested), or default if not set/empty
        
    Raises:
        ValueError: If required=True and value is missing or empty after strip
    
    Examples:
        >>> get_env_str("MY_VAR")  # Returns None if not set
        >>> get_env_str("MY_VAR", default="fallback")
        >>> get_env_str("MY_VAR", required=True)  # Raises if not set
        >>> get_env_str("MY_VAR", strip=False)  # Preserves whitespace
    """
    value = os.getenv(name)
    
    if value is None:
        if required:
            raise ValueError(
                f"Required environment variable '{name}' is not set. "
                f"Please add it to your .env file or environment."
            )
        return default
    
    if strip:
        value = value.strip()
    
    if not value:  # Empty string after strip
        if required:
            raise ValueError(
                f"Required environment variable '{name}' is empty (or whitespace-only). "
                f"Please set a valid value in your .env file or environment."
            )
        return default
    
    return value


def get_env_bool(name: str, default: bool = False) -> bool:
    """
    Read a boolean environment variable.
    
    Truthy values: "1", "true", "yes", "on" (case-insensitive)
    Falsy values: "0", "false", "no", "off", "" or not set
    
    Args:
        name: Environment variable name
        default: Default value if not set
    
    Returns:
        Boolean value
    """
    value = os.getenv(name, "").strip().lower()
    
    if not value:
        return default
    
    return value in ("1", "true", "yes", "on")
