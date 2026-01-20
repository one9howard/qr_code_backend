"""
Helper utilities for user management and tier checking.
"""
from datetime import datetime


def is_pro(user):
    """
    Check if user has active Pro subscription.
    
    Args:
        user: User model instance
        
    Returns:
        bool: True if user has active Pro subscription
    """
    if not user or not user.subscription_status:
        return False
    
    if user.subscription_status not in ['active', 'trialing']:
        return False
    
    if user.subscription_end_date:
        try:
            # Handle both ISO string and datetime
            if isinstance(user.subscription_end_date, str):
                end_date = datetime.fromisoformat(user.subscription_end_date)
            else:
                end_date = user.subscription_end_date
            
            if end_date < datetime.now():
                return False
        except (ValueError, AttributeError):
            # If we can't parse the date, be conservative
            return False
    
    return True


def get_user_display_name(user):
    """
    Get a friendly display name for the user.
    
    Tries to get name from:
    1. Agent name (first name only)
    2. Email username (capitalized)
    
    Args:
        user: User model instance
        
    Returns:
        str: Display-friendly name
    """
    from database import get_db
    
    if not user:
        return "Guest"
    
    # Try to get agent name
    try:
        db = get_db()
        agent = db.execute(
            "SELECT name FROM agents WHERE user_id = %s LIMIT 1",
            (user.id,)
        ).fetchone()
        
        if agent and agent['name']:
            # Return first name only
            return agent['name'].split()[0]
    except Exception:
        pass
    
    # Fallback to email username
    try:
        username = user.email.split('@')[0]
        # Capitalize and make more readable
        return username.replace('.', ' ').replace('_', ' ').title()
    except Exception:
        return "User"
