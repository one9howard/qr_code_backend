"""
Network utilities for client IP handling.

Provides get_client_ip() that works correctly with or without ProxyFix middleware.
"""
from flask import request


def get_client_ip() -> str:
    """
    Get the client's IP address.
    
    When ProxyFix is enabled (TRUST_PROXY_HEADERS=true behind a proxy),
    request.remote_addr is automatically set to the real client IP from
    X-Forwarded-For headers.
    
    When ProxyFix is disabled (direct access or TRUST_PROXY_HEADERS=false),
    request.remote_addr is the direct connection IP.
    
    Returns:
        Client IP address string, or empty string if not available
    """
    return request.remote_addr or ""
