"""Helpers for safely logging connection strings and secrets."""

from __future__ import annotations

from urllib.parse import urlparse


def redact_database_url(url: str) -> str:
    """Return DATABASE_URL with password masked for logs/errors."""
    raw = (url or "").strip()
    if not raw:
        return "EMPTY_DATABASE_URL"
    try:
        parsed = urlparse(raw)
        scheme = parsed.scheme or "postgresql"
        host = parsed.hostname or "unknown-host"
        port = f":{parsed.port}" if parsed.port else ""
        db_name = parsed.path.lstrip("/") or "unknown-db"
        if parsed.username:
            return f"{scheme}://{parsed.username}:****@{host}{port}/{db_name}"
        return f"{scheme}://{host}{port}/{db_name}"
    except Exception:
        return "INVALID_DATABASE_URL"
