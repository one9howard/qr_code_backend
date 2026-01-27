from datetime import datetime, timezone
from database import get_db
# Import canonical constants
from constants import PAID_STATUSES

def is_paid_order(order_dict_or_row):
    """
    Canonical check for whether an order is considered paid/valid for entitlement.
    """
    if not order_dict_or_row:
        return False
    # Handle dict/row access safely
    status = order_dict_or_row.get('status') if isinstance(order_dict_or_row, dict) else order_dict_or_row['status']
    return status in PAID_STATUSES

def property_is_paid(property_id, user_id=None):
    """
    Canonical check: Is this property 'unlocked' for the user?
    
    A property is unlocked if:
    1. Owner has active PRO subscription.
    2. OR there is a PAID order of type 'listing_unlock', 'sign', or 'smart_sign'.
       (Explicitly EXCLUDES 'listing_kit').
    """
    if property_id is None:
        return False

    db = get_db()
    
    # 1. Check Subscription (if user_id provided or derived from property owner)
    # If user_id is NOT provided, we must look up the agent->user owning the property
    if not user_id:
        owner_row = db.execute("""
            SELECT u.subscription_status, u.id as user_id
            FROM properties p
            JOIN agents a ON p.agent_id = a.id
            JOIN users u ON a.user_id = u.id
            WHERE p.id = %s
        """, (property_id,)).fetchone()
        
        if owner_row:
            user_id = owner_row['user_id']
            from services.subscriptions import is_subscription_active
            if is_subscription_active(owner_row['subscription_status']):
                return True
    else:
        # If user_id provided, check that specific user's sub? 
        # Usually we care about the PROPERTY OWNER's status.
        # But let's assume if user_id is passed, we check their sub status if they own it.
        # Ideally we stick to property owner lookup for robustness.
        # Let's fallback to the query above which is safer.
        pass

    # Re-run owner lookup if we didn't enter the block above or if we need to be sure
    # Actually, the logic in get_property_gating_status does the join.
    # Let's reuse that exact query structure for consistency.
    
    owner_query = """
        SELECT u.subscription_status
        FROM properties p
        JOIN agents a ON p.agent_id = a.id
        JOIN users u ON a.user_id = u.id
        WHERE p.id = %s
    """
    owner_row = db.execute(owner_query, (property_id,)).fetchone()
    
    from services.subscriptions import is_subscription_active
    if owner_row and is_subscription_active(owner_row['subscription_status']):
        return True

    # 2. Check for Paid Order (Canonical Entitlement)
    placeholders = ','.join(['%s'] * len(PAID_STATUSES))
    # Note: listing_kit is explicitly EXCLUDED
    query = f"""
        SELECT 1 FROM orders 
        WHERE property_id = %s 
        AND status IN ({placeholders})
        AND order_type IN ('listing_unlock', 'sign', 'smart_sign')
        LIMIT 1
    """
    has_order = db.execute(query, (property_id, *PAID_STATUSES)).fetchone()
    
    return bool(has_order)

            "expires_at": datetime | None,
            "days_remaining": int | None,
            "max_photos": int,
            "show_gallery": bool,
            "locked_reason": "unpaid" | "expired" | None
        }
    """
    if property_id is None:
        return {
            "is_paid": False,
            "is_expired": False,
            "expires_at": None,
            "days_remaining": None,
            "max_photos": 1,
            "show_gallery": False,
            "locked_reason": "unpaid"
        }

    db = get_db()
    
    # Use Canonical Helper for 'is_paid' state
    # This checks both Subscription and explicit Paid Orders
    is_paid = property_is_paid(property_id)
    
    # Determine 'paid_via' for UI/Logic if paid
    paid_via = None
    paid_source_order_id = None
    
    if is_paid:
        # Re-derive source for granular UI details if needed
        # (Optimized: we could have property_is_paid return metadata, but keeping it boolean is cleaner for other callers)
        
        # 1. Check Sub again (lightwieght)
        owner_row = db.execute("""
            SELECT u.subscription_status
            FROM properties p
            JOIN agents a ON p.agent_id = a.id
            JOIN users u ON a.user_id = u.id
            WHERE p.id = %s
        """, (property_id,)).fetchone()
        
        from services.subscriptions import is_subscription_active
        if owner_row and is_subscription_active(owner_row['subscription_status']):
            paid_via = 'subscription'
        else:
            # 2. Must be an order
            placeholders = ','.join(['%s'] * len(PAID_STATUSES))
            query = f"""
                SELECT id, order_type FROM orders 
                WHERE property_id = %s 
                AND status IN ({placeholders})
                AND order_type IN ('listing_unlock', 'sign', 'smart_sign')
                ORDER BY created_at DESC
                LIMIT 1
            """
            row = db.execute(query, (property_id, *PAID_STATUSES)).fetchone()
            if row:
                paid_source_order_id = row['id']
                if row['order_type'] == 'listing_unlock':
                    paid_via = 'listing_unlock'
                else:
                    paid_via = 'sign_order'


    # 3. Get expiry info from property
    prop = db.execute(
        "SELECT expires_at FROM properties WHERE id = %s",
        (property_id,)
    ).fetchone()
    
    expires_at = None
    is_expired = False
    days_remaining = None
    locked_reason = None
    
    if prop:
        expires_raw = prop['expires_at']
        if isinstance(expires_raw, str):
            try:
                expires_at = datetime.fromisoformat(expires_raw.replace(' ', 'T'))
            except ValueError:
                expires_at = None
        else:
            expires_at = expires_raw
            
        if expires_at and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

    # 4. Strict Gating Logic (Priority-based)
    if is_paid:
        # Priority 1: Explicitly Paid (Subscription or Order)
        is_expired = False
        locked_reason = None
        days_remaining = None 
            
    elif expires_at is None:
        # Priority 2: NULL means NO EXPIRY (Legacy/Pro/Unlocked behavior)
        # "NULL means no expiry"
        is_expired = False
        locked_reason = None
        days_remaining = None

    else:
        # Priority 3: Has expiry date -> check it
        now = datetime.now(timezone.utc)
        if expires_at < now:
            is_expired = True
            days_remaining = 0
            locked_reason = "trial_expired"
        else:
            is_expired = False
            delta = expires_at - now
            days_remaining = max(0, delta.days)
            locked_reason = None
    
    # 5. Calculate limits
    # Paid = Max capabilities
    max_photos = 50 if is_paid else 1
    show_gallery = is_paid
    
    return {
        "is_paid": is_paid,
        "paid_via": paid_via,
        "paid_source_order_id": paid_source_order_id,
        "is_expired": is_expired,
        "expires_at": expires_at,
        "days_remaining": days_remaining,
        "max_photos": max_photos,
        "show_gallery": show_gallery,
        "locked_reason": locked_reason
    }

def can_create_property(user_id):
    """
    Check if user can create a new property based on subscription status and limits.
    
    Free tier limits:
    - Maximum active properties controlled by FREE_TIER_MAX_ACTIVE_PROPERTIES env var (default: 1)
    - "Active" = property exists and is not deleted
    
    Args:
        user_id: User ID to check
        
    Returns:
        dict: {
            "allowed": bool,
            "reason": str | None,  # 'max_listings' if blocked
            "limit": int,          # free tier limit
            "current": int         # current active property count
        }
    """
    import os
    from services.subscriptions import is_subscription_active
    
    db = get_db()
    
    # 1. Check if user is Pro
    user = db.execute(
        "SELECT subscription_status FROM users WHERE id = %s",
        (user_id,)
    ).fetchone()
    
    if user and is_subscription_active(user['subscription_status']):
        # Pro users have no limit
        return {
            "allowed": True,
            "reason": None,
            "limit": None,
            "current": 0
        }
    
    # 2. Free tier - check property count
    free_limit = int(os.environ.get("FREE_TIER_MAX_ACTIVE_PROPERTIES", "1"))
    
    # Count all properties owned by user (active = exists in DB)
    # Properties are considered "active" if they exist - simple MVP definition
    count_result = db.execute(
        """
        SELECT COUNT(*) as cnt
        FROM properties p
        JOIN agents a ON p.agent_id = a.id
        WHERE a.user_id = %s
        """,
        (user_id,)
    ).fetchone()
    
    current_count = count_result['cnt'] if count_result else 0
    
    if current_count >= free_limit:
        return {
            "allowed": False,
            "reason": "max_listings",
            "limit": free_limit,
            "current": current_count
        }
    
    return {
        "allowed": True,
        "reason": None,
        "limit": free_limit,
        "current": current_count
    }
