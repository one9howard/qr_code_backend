"""
Stripe Checkout Service Module

Provides helper functions for attempt-based idempotency when creating
Stripe Checkout Sessions. This prevents the "idempotent requests can only 
be used with the same parameters" error by tracking each checkout attempt
in the database.
"""
import json
import hashlib
from uuid import uuid4
from datetime import datetime
from database import get_db
from utils.timestamps import utc_iso


def normalize_checkout_params(params: dict) -> dict:
    """
    Normalize checkout parameters for consistent hashing.
    Recursively sorts keys and handles nested structures.
    
    Args:
        params: The checkout session parameters dict
        
    Returns:
        Normalized dict with sorted keys
    """
    def _normalize(obj):
        if isinstance(obj, dict):
            return {k: _normalize(v) for k, v in sorted(obj.items())}
        elif isinstance(obj, list):
            return [_normalize(item) for item in obj]
        else:
            return obj
    
    return _normalize(params)


def compute_params_hash(params: dict) -> str:
    """
    Compute SHA256 hash of normalized checkout parameters.
    
    Args:
        params: The checkout session parameters dict
        
    Returns:
        Hex digest of SHA256 hash
    """
    normalized = normalize_checkout_params(params)
    json_str = json.dumps(normalized, separators=(',', ':'), sort_keys=True)
    return hashlib.sha256(json_str.encode('utf-8')).hexdigest()


def create_checkout_attempt(user_id: int | None, purpose: str, params: dict, order_id: int | None = None) -> dict:
    """
    Create a new checkout attempt record in the database.
    
    Args:
        user_id: The user's ID (can be None for guest checkouts)
        purpose: The purpose of the checkout (e.g., "subscription_upgrade", "sign_order")
        params: The checkout session parameters to hash
        order_id: Optional order ID for sign order checkouts
        
    Returns:
        Dict with attempt details including attempt_token and idempotency_key
    """
    db = get_db()
    
    attempt_token = uuid4().hex
    idempotency_key = f"{purpose}_{attempt_token}"
    params_hash = compute_params_hash(params)
    now = utc_iso()
    
    # RETURNING id required
    cursor = db.execute('''
        INSERT INTO checkout_attempts 
        (attempt_token, user_id, purpose, status, idempotency_key, 
         params_hash, order_id, created_at, updated_at)
        VALUES (%s, %s, %s, 'created', %s, %s, %s, %s, %s)
        RETURNING id
    ''', (attempt_token, user_id, purpose, idempotency_key, params_hash, order_id, now, now))
    db.commit()
    
    return {
        'id': cursor.fetchone()['id'],
        'attempt_token': attempt_token,
        'user_id': user_id,
        'purpose': purpose,
        'status': 'created',
        'idempotency_key': idempotency_key,
        'params_hash': params_hash,
        'order_id': order_id,
        'stripe_session_id': None,
        'stripe_customer_id': None,
        'error_message': None,
        'created_at': now,
        'updated_at': now
    }


def get_checkout_attempt(attempt_token: str) -> dict | None:
    """
    Retrieve a checkout attempt by its token.
    
    Args:
        attempt_token: The unique attempt token
        
    Returns:
        Dict with attempt details or None if not found
    """
    db = get_db()
    row = db.execute(
        "SELECT * FROM checkout_attempts WHERE attempt_token = %s",
        (attempt_token,)
    ).fetchone()
    
    if row is None:
        return None
    
    return dict(row)


def update_attempt_status(attempt_token: str, status: str, **kwargs) -> bool:
    """
    Update the status and optional fields of a checkout attempt.
    
    Args:
        attempt_token: The unique attempt token
        status: New status (e.g., 'session_created', 'completed', 'failed')
        **kwargs: Optional fields to update:
            - stripe_session_id: The Stripe session ID
            - stripe_customer_id: The Stripe customer ID
            - error_message: Error message if failed
            
    Returns:
        True if updated, False if attempt not found
    """
    db = get_db()
    now = utc_iso()
    
    # Build dynamic update query
    update_fields = ['status = %s', 'updated_at = %s']
    values = [status, now]
    
    if 'stripe_session_id' in kwargs:
        update_fields.append('stripe_session_id = %s')
        values.append(kwargs['stripe_session_id'])
        
    if 'stripe_customer_id' in kwargs:
        update_fields.append('stripe_customer_id = %s')
        values.append(kwargs['stripe_customer_id'])
        
    if 'error_message' in kwargs:
        update_fields.append('error_message = %s')
        values.append(kwargs['error_message'])
    
    values.append(attempt_token)
    
    query = f"UPDATE checkout_attempts SET {', '.join(update_fields)} WHERE attempt_token = %s"
    cursor = db.execute(query, values)
    db.commit()
    
    return cursor.rowcount > 0


def validate_attempt_params(attempt: dict, params: dict) -> bool:
    """
    Validate that the provided params match the stored attempt's params_hash.
    
    Args:
        attempt: The checkout attempt record
        params: The checkout parameters to validate
        
    Returns:
        True if params match, False otherwise
    """
    current_hash = compute_params_hash(params)
    return attempt['params_hash'] == current_hash


def get_latest_attempt_for_order(order_id: int, purpose: str) -> dict | None:
    """
    Get the most recent checkout attempt for a given order.
    
    Args:
        order_id: The order ID to look up
        purpose: The purpose of the checkout (e.g., "sign_order")
        
    Returns:
        Dict with attempt details or None if not found
    """
    db = get_db()
    row = db.execute(
        """SELECT * FROM checkout_attempts 
           WHERE order_id = %s AND purpose = %s 
           ORDER BY created_at DESC LIMIT 1""",
        (order_id, purpose)
    ).fetchone()
    
    if row is None:
        return None
    
    return dict(row)
