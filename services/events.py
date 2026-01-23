import os
import json
import hashlib
from datetime import datetime
from flask import request, g, has_request_context, current_app
from config import SECRET_KEY
from models import AppEvent

# --- Quick Config ---
MAX_PAYLOAD_SIZE = 8192  # 8KB
SECRET_SALT = SECRET_KEY if SECRET_KEY else "fallback-salt"

# --- Allowlists ---
SERVER_EVENTS = {
    "property_view",
    "lead_submitted",
    "lead_notification_sent",
    "lead_notification_failed",
    "checkout_started",
    "subscription_activated"
}

CLIENT_EVENTS = {
    "gated_content_attempt",
    "upsell_shown",
    "upsell_dismissed",
    "upsell_cta_clicked",
    "cta_click"
}

FORBIDDEN_KEYS = {
    "email", "phone", "message", "name", "address", 
    "lead_message", "password", "token", "credit_card", "cvc"
}

def _hash_value(value):
    """SHA256 hash with secret salt."""
    if not value: return None
    return hashlib.sha256(f"{value}{SECRET_SALT}".encode('utf-8')).hexdigest()

def _clean_payload(payload):
    """
    Recursively remove forbidden keys and enforce size limits.
    Returns cleaned dict.
    """
    if not isinstance(payload, dict):
        return {}
    
    cleaned = {}
    for k, v in payload.items():
        if k.lower() in FORBIDDEN_KEYS:
            continue
        # Check nested dicts if needed, though usually flat is better.
        # Minimal recursion for simple objects
        if isinstance(v, dict):
             cleaned[k] = _clean_payload(v)
        else:
             cleaned[k] = v
             
    # Size check (rough estimate using json dump)
    try:
        serialized = json.dumps(cleaned)
        if len(serialized) > MAX_PAYLOAD_SIZE:
            current_app.logger.warning(f"[Events] Payload too large ({len(serialized)} bytes). Truncating.")
            return {"error": "payload_too_large"}
    except Exception:
        return {"error": "serialization_failed"}
        
    return cleaned

def track_event(event_type, source="server", user_id=None, property_id=None, sign_asset_id=None, order_id=None, qr_code=None, payload=None, meta=None):
    """
    Track a canonical event.
    Swallows exceptions to prevent breaking user flow.
    
    Args:
        event_type: String name of event.
        source: "server" or "client".
        ... standard IDs ...
        payload: Dict of data to store.
        meta: Legacy alias for payload (support for old calls).
    """
    try:
        # Legacy Support: Map meta -> payload
        if payload is None and meta is not None:
            payload = meta

        # 1. Validation
        allowed = SERVER_EVENTS if source == "server" else CLIENT_EVENTS
        if event_type not in allowed:
             # Log but don't crash
             # current_app.logger.warning(f"[Events] Rejected unknown event_type: {event_type}")
             return

        # 2. Payload Prep
        if payload is None: payload = {}
        safe_payload = _clean_payload(payload)
        
        # Auto-add version
        if "version" not in safe_payload:
            safe_payload["version"] = 1
            
        # 3. Request Context Metadata
        session_id = None
        req_id = None
        ip_hash = None
        ua_hash = None
        
        if has_request_context():
            # Request ID
            req_id = getattr(g, 'request_id', None)
            
            # Session ID (Cookie)
            session_id = request.cookies.get('sid')
            
            # Hashes
            ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()
            ua = request.user_agent.string if request.user_agent else ""
            
            ip_hash = _hash_value(ip)
            ua_hash = _hash_value(ua)
            
        # 4. Commit to DB
        AppEvent.create(
            event_type=event_type,
            source=source,
            user_id=user_id,
            property_id=property_id,
            sign_asset_id=sign_asset_id,
            order_id=order_id,
            qr_code=qr_code,
            session_id=session_id,
            request_id=req_id,
            ip_hash=ip_hash,
            ua_hash=ua_hash,
            payload=safe_payload
        )
        
    except Exception as e:
        # Fail silent
        if has_request_context():
            current_app.logger.warning(f"[Events] Failed to track {event_type}: {e}")
        else:
            print(f"[Events] Failed to track {event_type}: {e}")
