"""
Entitlements Service - Check user entitlements for specific products.

This module provides entitlement checks that are SEPARATE from property gating.
For example, listing_kit entitlement does NOT unlock property paid status.
"""
from database import get_db
from constants import PAID_STATUSES


def has_paid_listing_kit(user_id: int, property_id: int) -> bool:
    """
    Check if user has a paid listing_kit order for this property.
    
    Returns True if there exists an order with:
      - user_id = user_id
      - property_id = property_id  
      - order_type = 'listing_kit'
      - status IN PAID_STATUSES
      
    This is separate from property gating - a paid listing_kit enables
    free kit regeneration but does NOT unlock the property.
    
    Args:
        user_id: The user ID to check
        property_id: The property ID to check
        
    Returns:
        True if user has paid for listing kit for this property
    """
    db = get_db()
    
    placeholders = ','.join(['%s'] * len(PAID_STATUSES))
    query = f"""
        SELECT 1 FROM orders 
        WHERE user_id = %s 
          AND property_id = %s 
          AND order_type = 'listing_kit'
          AND status IN ({placeholders})
        LIMIT 1
    """
    
    row = db.execute(query, (user_id, property_id, *PAID_STATUSES)).fetchone()
    return row is not None
