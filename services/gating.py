from datetime import datetime, timezone
from database import get_db
from constants import PAID_STATUSES


def get_property_gating_status(property_id):
    """
    Single source of truth for property paid/expiry status.
    
    Returns:
        dict: {
            "is_paid": bool,
            "is_expired": bool,
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
    
    
    # 1. Check for Subscription Status (HIGHEST PRIORITY)
    # If owner has active subscription, property is PAID via subscription.
    # We need to fetch the owner's subscription status.
    paid_via = None
    paid_source_order_id = None
    
    # Fetch owner info with correct joins
    owner_query = """
        SELECT u.subscription_status
        FROM properties p
        JOIN agents a ON p.agent_id = a.id
        JOIN users u ON a.user_id = u.id
        WHERE p.id = %s
    """
    owner_row = db.execute(owner_query, (property_id,)).fetchone()
    
    from services.subscriptions import is_subscription_active
    # Use robust check instead of just 'active'
    if owner_row and is_subscription_active(owner_row['subscription_status']):
        paid_via = 'subscription'
        is_paid = True
    else:
        # 2. Check for any PAID order associated with this property
        # Check for listing_unlock OR sign order
        placeholders = ','.join(['%s'] * len(PAID_STATUSES))
        query = f"""
            SELECT id, order_type FROM orders 
            WHERE property_id = %s 
            AND status IN ({placeholders})
            ORDER BY created_at DESC
            LIMIT 1
        """
        row = db.execute(query, (property_id, *PAID_STATUSES)).fetchone()
        
        if row:
            is_paid = True
            order_type = row['order_type']
            paid_source_order_id = row['id']
            # Map order_type to paid_via
            if order_type == 'listing_unlock':
                paid_via = 'listing_unlock'
            elif order_type == 'listing_kit':
                paid_via = 'listing_kit'
            elif order_type == 'sign':
                paid_via = 'sign_order'
            else:
                paid_via = 'sign_order' # Default fallback for legacy orders
        else:
            is_paid = False

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
        # Priority 1 & 2: Explicitly Paid (Subscription or Order)
        is_expired = False
        locked_reason = None
        # For subscription/paid properties, we don't show a countdown
        days_remaining = None 
            
    else:
        # Priority 3: Free Tier (Expires)
        if expires_at is None:
            # CRITICAL: NULL expires_at means UNPAID/EXPIRED (not infinite)
            is_expired = True
            days_remaining = 0
            locked_reason = "unpaid"
        else:
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

def get_smart_sign_assets(user_id):
    """
    Fetch all SmartSign assets owned by the user.
    Returns list of dicts.
    """
    db = get_db()
    rows = db.execute("""
        SELECT * FROM sign_assets 
        WHERE user_id = %s 
        ORDER BY created_at DESC
    """, (user_id,)).fetchall()
    return [dict(r) for r in rows]

class GatingService:
    def assign_smart_sign(self, user_id, asset_id, property_id):
        """
        Assigns a SmartSign asset to a property.
        Validates ownership and ensures 1-to-1 mapping if strictly enforced,
        or updates the pointer.
        """
        db = get_db()
        
        # Verify ownership
        asset = db.execute(
            "SELECT * FROM sign_assets WHERE id = %s AND user_id = %s",
            (asset_id, user_id)
        ).fetchone()
        
        if not asset:
            return False, "Asset not found or access denied."
            
        # Verify property ownership
        # Usually checking agent_id -> user_id link
        prop = db.execute("""
            SELECT p.id 
            FROM properties p
            JOIN agents a ON p.agent_id = a.id
            WHERE p.id = %s AND a.user_id = %s
        """, (property_id, user_id)).fetchone()
        
        if not prop:
            return False, "Property not found or access denied."
            
        # Perform Assignment
        # If asset was assigned elsewhere, we overwrite.
        try:
            db.execute(
                "UPDATE sign_assets SET property_id = %s, updated_at = NOW() WHERE id = %s",
                (property_id, asset_id)
            )
            db.commit()
            return True, "Assigned successfully."
        except Exception as e:
            return False, f"Database error: {str(e)}"

    def unassign_smart_sign(self, user_id, asset_id):
        """
        Unassigns a property from a SmartSign asset.
        """
        db = get_db()
         # Verify ownership
        asset = db.execute(
            "SELECT * FROM sign_assets WHERE id = %s AND user_id = %s",
            (asset_id, user_id)
        ).fetchone()
        
        if not asset:
            return False, "Asset not found."
            
        try:
            db.execute(
                "UPDATE sign_assets SET property_id = NULL, updated_at = NOW() WHERE id = %s",
                (asset_id,)
            )
            db.commit()
            return True, "Unassigned successfully."
        except Exception as e:
            return False, f"Database error: {str(e)}"

gating_service = GatingService()


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
