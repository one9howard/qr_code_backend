"""
Event tracking service for minimal analytics.

Best-effort tracking - failures are logged but don't break main flow.
"""
import json
from database import get_db


def track_event(event_name, user_id=None, property_id=None, order_id=None, meta=None):
    """
    Track an event to the database.
    
    This is best-effort tracking - failures are caught and logged
    to avoid breaking the main application flow.
    
    Args:
        event_name: Name of the event (e.g., 'upgrade_prompt_shown', 'kit_checkout_started')
        user_id: Optional user ID
        property_id: Optional property ID
        order_id: Optional order ID
        meta: Optional dict of additional metadata (stored as JSONB)
    
    Event names used:
        - upgrade_prompt_shown: User saw an upgrade prompt
        - kit_checkout_started: User started listing kit checkout
        - kit_purchased: Listing kit purchase completed
        - sign_purchased: SmartSign purchase completed
    """
    try:
        db = get_db()
        
        meta_json = None
        if meta:
            meta_json = json.dumps(meta)
        
        db.execute(
            """
            INSERT INTO events (user_id, event_name, property_id, order_id, meta_json, created_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
            """,
            (user_id, event_name, property_id, order_id, meta_json)
        )
        db.commit()
        
    except Exception as e:
        # Best-effort tracking - log error but don't crash
        # Don't print sensitive data (no user IDs, just event name)
        print(f"[Events] Failed to track event '{event_name}': {type(e).__name__}")
