import logging
# import sqlite3  <-- Removed
from database import get_db
import utils.storage as storage_module  # Module reference for testability
from utils.filenames import make_sign_asset_basename

logger = logging.getLogger(__name__)

def delete_property_fully(property_id: int):
    """
    Completely and safely delete a property, its assets, and all related records.
    
    Order of operations:
    1. Delete Storage Assets (Photos, QRs, PDFs, Previews)
    2. Delete DB records in FK-safe order (transactional)
    
    Args:
        property_id: ID of the property to delete
    
    Returns:
        bool: True if successful, False if DB error (storage errors logged but ignored)
    """
    db = get_db()
    storage = storage_module.get_storage()
    
    # 1. Gather Data (Read-only phase)
    # We need data to know what storage keys to delete
    
    # Get Property Info (QR code)
    prop = db.execute("SELECT id, qr_code FROM properties WHERE id = %s", (property_id,)).fetchone()
    if not prop:
        return True # Already gone
    
    qr_code = prop['qr_code']
    
    # Get Photos
    photos = db.execute("SELECT filename FROM property_photos WHERE property_id = %s", (property_id,)).fetchall()
    
    # Get Orders (for PDFs and Previews)
    orders = db.execute("SELECT id, sign_pdf_path, sign_size FROM orders WHERE property_id = %s", (property_id,)).fetchall()
    
    # 2. Delete Storage Assets (Best Effort)
    # Errors here should NOT roll back the DB deletion, so we just log them.
    
    # Delete Property Photos
    for photo in photos:
        if photo['filename']:
            try:
                storage.delete(photo['filename'])
            except Exception as e:
                logger.warning(f"[Delete] Failed to delete photo {photo['filename']}: {e}")
                
    # Delete QR Image
    if qr_code:
        try:
            qr_key = f"qr/{qr_code}.png"
            storage.delete(qr_key)
        except Exception as e:
            logger.warning(f"[Delete] Failed to delete QR {qr_key}: {e}")
            
    # Delete Order Assets
    for order in orders:
        # PDF
        if order['sign_pdf_path']:
            try:
                storage.delete(order['sign_pdf_path'])
            except Exception as e:
                logger.warning(f"[Delete] Failed to delete PDF {order['sign_pdf_path']}: {e}")
        
        # Preview
        # deterministic: previews/order_{order_id}/{basename}.webp
        # basename comes from make_sign_asset_basename
        if order['sign_size']:
            try:
                basename = make_sign_asset_basename(order['id'], order['sign_size'])
                preview_key = f"previews/order_{order['id']}/{basename}.webp"
                storage.delete(preview_key)
            except Exception as e:
                logger.warning(f"[Delete] Failed to delete preview {preview_key}: {e}")
                
    # Delete Print Job Assets
    # Fetch job_ids related to these orders
    if orders:
        order_ids = [o['id'] for o in orders]
        placeholders = ','.join(['%s'] * len(order_ids))
        print_jobs = db.execute(
            f"SELECT filename FROM print_jobs WHERE order_id IN ({placeholders})", 
            (*order_ids,)
        ).fetchall()
        
        for job in print_jobs:
            if job['filename']:
                try:
                    storage.delete(job['filename'])
                except Exception as e:
                    logger.warning(f"[Delete] Failed to delete print job asset {job['filename']}: {e}")

    # 3. Delete DB Records (Transactional)
    try:
        # Order satisfies Postgres cascading requirements
        
        # lead_notifications (FK -> leads)
        db.execute("""
            DELETE FROM lead_notifications 
            WHERE lead_id IN (SELECT id FROM leads WHERE property_id = %s)
        """, (property_id,))
        
        # leads (FK -> properties)
        db.execute("DELETE FROM leads WHERE property_id = %s", (property_id,))
        
        # order_agent_snapshot (FK -> orders)
        db.execute("""
            DELETE FROM order_agent_snapshot 
            WHERE order_id IN (SELECT id FROM orders WHERE property_id = %s)
        """, (property_id,))
        
        # checkout_attempts (FK -> orders, if column exists)
        # Check if table exists first to be safe or just try/except
        try:
            db.execute("""
                DELETE FROM checkout_attempts 
                WHERE order_id IN (SELECT id FROM orders WHERE property_id = %s)
            """, (property_id,))
        except Exception:
            # Table or column might not exist in some states
            pass
            
        # print_jobs (FK -> orders implicitly via order_id)
        # Need to delete print_jobs first if orders prevents it?
        # Typically print_jobs references orders? 
        # database.py schema for print_jobs: order_id INTEGER. No FOREIGN KEY constraint mentioned in `database.py` line 639.
        # But good practice to clean up.
        db.execute(f"""
            DELETE FROM print_jobs 
            WHERE order_id IN (SELECT id FROM orders WHERE property_id = %s)
        """, (property_id,))
            
        # orders (FK -> properties)
        db.execute("DELETE FROM orders WHERE property_id = %s", (property_id,))
        
        # qr_scans (FK -> properties)
        db.execute("DELETE FROM qr_scans WHERE property_id = %s", (property_id,))
        
        # property_views (FK -> properties)
        db.execute("DELETE FROM property_views WHERE property_id = %s", (property_id,))
        
        # property_photos (FK -> properties)
        db.execute("DELETE FROM property_photos WHERE property_id = %s", (property_id,))
        
        # properties
        db.execute("DELETE FROM properties WHERE id = %s", (property_id,))
        
        db.commit()
        logger.info(f"[Delete] Successfully deleted property {property_id} and related data.")
        return True
        
    except Exception as e:
        db.rollback()
        logger.error(f"[Delete] DB Error deleting property {property_id}: {e}")
        # Storage assets are already gone, but that's acceptable (orphaned DB records is worse)
        return False
