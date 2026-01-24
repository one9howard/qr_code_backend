import os
import json
import hashlib
from datetime import datetime
from flask import request, g, has_request_context, current_app
from config import SECRET_KEY, APP_STAGE
from models import AppEvent

# --- Config ---
MAX_PAYLOAD_SIZE = 8192  # 8KB
SECRET_SALT = SECRET_KEY if SECRET_KEY else "fallback-salt"

# --- Allowlists ---
SERVER_EVENTS = {
    "property_view",
    "lead_submitted",
    "lead_notification_sent",
    "lead_notification_failed",
    "checkout_started",
    "subscription_activated",
    "agent_action_executed",
    "agent_action_failed",
    "upgrade_prompt_shown",
    "kit_checkout_started",
    "smart_sign_scan"  # SmartSign scans (including unassigned/unactivated)
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
    "lead_message", "password", "token", "credit_card", "cvc",
    "buyer_name", "buyer_email", "buyer_phone"
}

def _hash_value(value):
    """SHA256 hash with secret salt."""
    if not value: return None
    return hashlib.sha256(f"{value}{SECRET_SALT}".encode('utf-8')).hexdigest()

def _clean_payload(payload):
    """
    Recursively remove forbidden keys and enforce size limits.
    Returns (cleaned_dict, was_stripped_bool).
    """
    if not isinstance(payload, dict):
        return {}, False
    
    cleaned = {}
    stripped = False
    
    for k, v in payload.items():
        # Check key
        if any(bad in k.lower() for bad in FORBIDDEN_KEYS):
            stripped = True
            continue
            
        # Check value (recursive for dict)
        if isinstance(v, dict):
             sub_clean, sub_stripped = _clean_payload(v)
             cleaned[k] = sub_clean
             if sub_stripped: stripped = True
        else:
             cleaned[k] = v
             
    return cleaned, stripped

def track_event(event_type, *, source="server", schema_version=1, environment=None,
              actor_type="system", actor_id=None,
              subject_type=None, subject_id=None,
              user_id=None, property_id=None, sign_asset_id=None, order_id=None, qr_code=None,
              idempotency_key=None, payload=None, meta=None):
    """
    Track a canonical event with full AI-readiness context.
    Swallows exceptions to prevent breaking user flow.
    """
    try:
        # Legacy Support: Map meta -> payload
        if payload is None and meta is not None:
            payload = meta
            
        # 1. Validation
        allowed = SERVER_EVENTS if source == "server" else CLIENT_EVENTS
        if event_type not in allowed:
             # Log but don't crash. Return early.
             if has_request_context():
                 current_app.logger.warning(f"[Events] Rejected unknown event_type: {event_type} (source={source})")
             return

        # 2. Payload Prep
        if payload is None: payload = {}
        
        # PII Clean
        safe_payload, stripped = _clean_payload(payload)
        
        # Enforce rules
        if "version" not in safe_payload:
            safe_payload["version"] = 1
        if "context" not in safe_payload:
            safe_payload["context"] = {}
        
        if stripped:
            safe_payload["pii_stripped"] = True

        # Size check
        try:
            serialized = json.dumps(safe_payload)
            if len(serialized) > MAX_PAYLOAD_SIZE:
                if has_request_context():
                    current_app.logger.warning(f"[Events] Payload too large ({len(serialized)} bytes). Truncating.")
                return 
        except Exception:
             return

        # 3. Request Context Metadata
        session_id = None
        req_id = None
        ip_hash = None
        ua_hash = None
        
        if has_request_context():
            # Request ID
            req_id = getattr(g, 'request_id', None)
            if not req_id:
                req_id = request.headers.get('X-Request-ID')
            
            # Session ID (Cookie)
            session_id = request.cookies.get('sid')
            if not session_id and hasattr(g, 'sid'):
                session_id = g.sid
            
            # Hashes
            # Handle proxy headers safely
            if request.headers.getlist("X-Forwarded-For"):
               ip = request.headers.getlist("X-Forwarded-For")[0]
            else:
               ip = request.remote_addr
               
            if ip: ip = ip.split(',')[0].strip()
            
            ua = request.user_agent.string if request.user_agent else ""
            
            ip_hash = _hash_value(ip)
            ua_hash = _hash_value(ua)
            
        # Environment default
        env = environment if environment else (APP_STAGE if APP_STAGE else 'production')

        # 4. Commit to DB
        AppEvent.create(
            event_type=event_type,
            source=source,
            schema_version=schema_version,
            environment=env,
            actor_type=actor_type,
            actor_id=actor_id,
            subject_type=subject_type,
            subject_id=subject_id,
            user_id=user_id,
            property_id=property_id,
            sign_asset_id=sign_asset_id,
            order_id=order_id,
            qr_code=qr_code,
            session_id=session_id,
            request_id=req_id,
            idempotency_key=idempotency_key,
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
