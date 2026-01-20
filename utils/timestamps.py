"""
Standardized UTC timestamp utilities.

All timestamps in this application should use these functions to ensure
consistent format across database storage, API responses, and comparisons.

Format: "YYYY-MM-DD HH:MM:SS" (UTC)
"""
from datetime import datetime, timezone, timedelta
from typing import Optional


def utc_now() -> datetime:
    """
    Return current UTC time with timezone info.
    
    Use this instead of datetime.now() or datetime.utcnow() to ensure
    timezone-aware UTC timestamps.
    """
    return datetime.now(timezone.utc)


def utc_iso() -> str:
    """
    Return current UTC time as ISO-like string (space separator).
    
    Format: "YYYY-MM-DD HH:MM:SS"
    
    Uses space separator (not T).
    This format is also parseable by fromisoformat() in Python 3.11+.
    """
    return utc_now().strftime("%Y-%m-%d %H:%M:%S")


def utc_iso_with_ms() -> str:
    """
    Return current UTC time with milliseconds.
    
    Format: "YYYY-MM-DD HH:MM:SS.ffffff"
    """
    return utc_now().strftime("%Y-%m-%d %H:%M:%S.%f")


def parse_timestamp(s: Optional[str]) -> Optional[datetime]:
    """
    Parse a timestamp string to datetime, handling multiple formats.
    
    Handles:
    - "YYYY-MM-DD HH:MM:SS"
    - "YYYY-MM-DDTHH:MM:SS" (ISO 8601 with T)
    - "YYYY-MM-DD HH:MM:SS.ffffff" (with microseconds)
    - "YYYY-MM-DDTHH:MM:SS.ffffff" (ISO with microseconds)
    
    Returns:
        datetime object (timezone-naive) or None if input is None/empty
    """
    if not s:
        return None
    
    # Normalize: replace T with space for consistent parsing
    normalized = s.replace("T", " ")
    
    # Try parsing with microseconds first, then without
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(normalized, fmt)
        except ValueError:
            continue
    
    # Fallback: try fromisoformat (handles more edge cases)
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def days_ago(days: int) -> str:
    """
    Return UTC timestamp string for N days ago.
    
    Useful for analytics queries like "last 30 days".
    """
    past = utc_now() - timedelta(days=days)
    return past.strftime("%Y-%m-%d %H:%M:%S")


def minutes_ago(minutes: int) -> str:
    """
    Return UTC timestamp string for N minutes ago.
    
    Useful for rate limiting windows.
    """
    past = utc_now() - timedelta(minutes=minutes)
    return past.strftime("%Y-%m-%d %H:%M:%S")
