
# Valid subscription statuses that unlock Pro features
ACTIVE_SUBSCRIPTION_STATUSES = {"active", "trialing"}

def is_subscription_active(status: str) -> bool:
    """
    Determines if a user's subscription status grants Pro access.
    
    Args:
        status (str): The subscription status string (e.g. 'active', 'trialing', 'canceled', 'past_due')
        
    Returns:
        bool: True if status is 'active' or 'trialing', False otherwise.
    """
    if not status:
        return False
    return status.lower() in ACTIVE_SUBSCRIPTION_STATUSES
