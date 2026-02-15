import logging
from datetime import datetime, timezone
from database import get_db
import utils.storage as storage_module  # Module reference for testability
from services.gating import get_property_gating_status

logger = logging.getLogger(__name__)

def cleanup_expired_properties(dry_run=False):
    """
    Find and delete expired properties that are NOT paid.
    Returns count of deleted properties.
    """
    db = get_db()
    storage = storage_module.get_storage()
    
    # Platform-agnostic now check
    # We fetch potentially expired rows, then filter in python for complex logic
    query = "SELECT id, address, expires_at FROM properties WHERE expires_at IS NOT NULL"
    rows = db.execute(query).fetchall()
    
    now = datetime.now(timezone.utc)
    deleted_count = 0
    
    for row in rows:
        pid = row['id']
        expires_at = row['expires_at']
        
        # Parse date
        if isinstance(expires_at, str):
            try:
                expires_at = datetime.fromisoformat(expires_at.replace(' ', 'T'))
            except:
                continue
        
        # Make timezone aware if naive
        if expires_at and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        
        if expires_at < now:
            # Double check: Is it paid?
            gating = get_property_gating_status(pid)
                
            if gating['is_paid']:
                # Should not happen if logic is correct, but self-heal
                logger.info(f"[Cleanup] Property {pid} is expired but PAID. Clearing expires_at.")
                if not dry_run:
                    db.execute("UPDATE properties SET expires_at = NULL WHERE id = %s", (pid,))
                    db.commit()
                continue
            
            # Verify no pending processing orders?
            # gating.is_paid checks PAID_STATUSES.
            # What if status is 'pending_payment'? 
            # If expired and pending_payment -> Delete. (User abandoned checkout > 24h ago).
            
            logger.info(f"[Cleanup] Deleting expired property {pid}")
            
            if dry_run:
                continue

            from services.properties import delete_property_fully
            if delete_property_fully(pid):
                deleted_count += 1

    return deleted_count
