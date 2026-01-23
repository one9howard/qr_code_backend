"""
Fulfillment Service - Phase 0 Complete

Handles order fulfillment:
1. Load order via raw SQL
2. Generate/validate PDF in storage
3. Enqueue to print_jobs via InternalQueueProvider
4. Update order status to 'submitted_to_printer'

Idempotent: If print_job already exists for order, returns success without duplicate.
"""
import logging
from database import get_db
from utils.storage import get_storage
from psycopg2.extras import Json

logger = logging.getLogger(__name__)

# Supported order types for fulfillment
SUPPORTED_ORDER_TYPES = ('sign', 'smart_sign', 'listing_kit')


def fulfill_order(order_id):
    """
    Generate/validate PDF and enqueue to print_jobs.
    Idempotent: safe to call multiple times.
    
    Returns:
        True on success (or if already fulfilled)
        False on error
    """
    db = get_db()
    storage = get_storage()
    
    # 1. Load order via raw SQL
    order = db.execute(
        "SELECT * FROM orders WHERE id = %s", (order_id,)
    ).fetchone()
    
    if not order:
        logger.error(f"[Fulfillment] Order {order_id} not found")
        return False
    
    order_type = order['order_type']
    status = order['status']
    
    print(f"[Fulfillment] Processing Order {order_id} (type={order_type}, status={status})")
    
    # 2. Validate status - only process 'paid' orders
    # If already 'submitted_to_printer', check idempotency
    if status == 'submitted_to_printer':
        # Check if print_job exists
        existing = db.execute(
            "SELECT job_id FROM print_jobs WHERE idempotency_key = %s",
            (f"order_{order_id}",)
        ).fetchone()
        if existing:
            print(f"[Fulfillment] Already fulfilled (job={existing['job_id']})")
            return True
    
    if status != 'paid':
        logger.warning(f"[Fulfillment] Order {order_id} status is '{status}', expected 'paid'")
        # Allow through if already submitted_to_printer for idempotency
        if status != 'submitted_to_printer':
            return False
    
    # 3. Validate order_type
    if order_type not in SUPPORTED_ORDER_TYPES:
        logger.error(f"[Fulfillment] Unsupported order_type: {order_type}")
        return False
    
    try:
        # 4. Ensure PDF exists in storage
        pdf_key = _ensure_pdf_in_storage(db, order, storage)
        
        if not pdf_key:
            logger.error(f"[Fulfillment] Failed to get/generate PDF for order {order_id}")
            return False
        
        # 5. Enqueue via InternalQueueProvider (handles idempotency)
        from services.fulfillment_providers.internal import InternalQueueProvider
        provider = InternalQueueProvider()
        
        # Build shipping data from order
        shipping_data = _build_shipping_data(db, order)
        
        job_id = provider.submit_order(order_id, shipping_data, pdf_key)
        
        # 6. Update order status
        db.execute("""
            UPDATE orders 
            SET status = 'submitted_to_printer',
                provider_job_id = %s,
                updated_at = NOW()
            WHERE id = %s
        """, (job_id, order_id))
        db.commit()
        
        print(f"[Fulfillment] Success: order {order_id} -> job {job_id}")
        return True
        
    except Exception as e:
        logger.error(f"[Fulfillment] Failed for order {order_id}: {e}", exc_info=True)
        return False


def _ensure_pdf_in_storage(db, order, storage):
    """
    Ensure PDF exists in storage.
    Returns storage key or None on failure.
    """
    order_id = order['id']
    order_type = order['order_type']
    print_product = order.get('print_product')
    sign_pdf_path = order.get('sign_pdf_path')
    
    # Check if we already have a valid PDF in storage
    if sign_pdf_path and storage.exists(sign_pdf_path):
        print(f"[Fulfillment] Using existing PDF: {sign_pdf_path}")
        return sign_pdf_path
    
    # Generate new PDF based on order type
    pdf_key = None
    
    if print_product == 'smart_sign' or order_type == 'smart_sign':
        pdf_key = _generate_smartsign_pdf(db, order, storage)
        
    elif print_product == 'listing_sign' or order_type == 'sign':
        pdf_key = _generate_listing_sign_pdf(db, order, storage)
        
    elif order_type == 'listing_kit':
        # Listing kit may not need print fulfillment, or has different flow
        logger.info(f"[Fulfillment] Listing kit order {order_id} - no print PDF needed")
        # Return a placeholder or handle differently
        return None
    
    # Persist new PDF key to order
    if pdf_key:
        db.execute(
            "UPDATE orders SET sign_pdf_path = %s, updated_at = NOW() WHERE id = %s",
            (pdf_key, order_id)
        )
        db.commit()
    
    return pdf_key


def _generate_smartsign_pdf(db, order, storage):
    """Generate SmartSign PDF and store in storage."""
    from services.pdf_smartsign import generate_smartsign_pdf
    
    order_id = order['id']
    sign_asset_id = order.get('sign_asset_id')
    
    # Load sign_asset if present
    asset = None
    if sign_asset_id:
        asset = db.execute(
            "SELECT * FROM sign_assets WHERE id = %s", (sign_asset_id,)
        ).fetchone()
    
    if not asset:
        # Try to get asset info from design_payload
        payload = order.get('design_payload') or {}
        if isinstance(payload, str):
            import json
            payload = json.loads(payload)
        
        asset_id_from_payload = payload.get('sign_asset_id')
        if asset_id_from_payload:
            asset = db.execute(
                "SELECT * FROM sign_assets WHERE id = %s", (asset_id_from_payload,)
            ).fetchone()
    
    if not asset:
        logger.error(f"[Fulfillment] No sign_asset found for SmartSign order {order_id}")
        return None
    
    # generate_smartsign_pdf returns storage key
    try:
        pdf_key = generate_smartsign_pdf(asset, order_id)
        print(f"[Fulfillment] Generated SmartSign PDF: {pdf_key}")
        return pdf_key
    except Exception as e:
        logger.error(f"[Fulfillment] SmartSign PDF generation failed: {e}")
        return None


def _generate_listing_sign_pdf(db, order, storage):
    """Generate Listing Sign PDF and store in storage."""
    from utils.pdf_generator import generate_pdf_sign
    from config import BASE_URL
    
    order_id = order['id']
    property_id = order.get('property_id')
    
    if not property_id:
        logger.error(f"[Fulfillment] No property_id for listing sign order {order_id}")
        return None
    
    # Load property
    prop = db.execute(
        "SELECT * FROM properties WHERE id = %s", (property_id,)
    ).fetchone()
    
    if not prop:
        logger.error(f"[Fulfillment] Property {property_id} not found")
        return None
    
    # Load agent info
    agent_id = prop.get('agent_id')
    agent = None
    if agent_id:
        agent = db.execute("""
            SELECT u.*, a.brokerage_name, a.custom_color 
            FROM agents a 
            JOIN users u ON a.user_id = u.id 
            WHERE a.id = %s
        """, (agent_id,)).fetchone()
    
    if not agent:
        # Fallback to order user
        agent = db.execute(
            "SELECT * FROM users WHERE id = %s", (order['user_id'],)
        ).fetchone()
    
    # Build QR URL
    qr_url = f"{BASE_URL}/s/{property_id}"
    
    # Get sign parameters
    sign_size = order.get('print_size') or '18x24'
    sign_color = None
    if agent:
        sign_color = agent.get('custom_color')
    
    # Generate PDF (returns storage key)
    try:
        pdf_key = generate_pdf_sign(
            address=prop.get('address', 'Address TBD'),
            beds=str(prop.get('beds', '')),
            baths=str(prop.get('baths', '')),
            sqft=str(prop.get('sqft', '')),
            price=_format_price(prop.get('price')),
            agent_name=agent.get('full_name', 'Agent') if agent else 'Agent',
            brokerage=agent.get('brokerage_name', '') if agent else '',
            agent_email=agent.get('email', '') if agent else '',
            agent_phone=agent.get('phone_number', '') if agent else '',
            sign_color=sign_color,
            sign_size=sign_size,
            order_id=order_id,
            qr_value=qr_url
        )
        print(f"[Fulfillment] Generated listing sign PDF: {pdf_key}")
        return pdf_key
    except Exception as e:
        logger.error(f"[Fulfillment] Listing sign PDF generation failed: {e}")
        return None


def _build_shipping_data(db, order):
    """Build shipping metadata for print job."""
    user_id = order['user_id']
    
    # Load user for shipping address
    user = db.execute(
        "SELECT * FROM users WHERE id = %s", (user_id,)
    ).fetchone()
    
    return {
        'order_id': order['id'],
        'order_type': order['order_type'],
        'user_id': user_id,
        'user_email': user.get('email') if user else None,
        'print_size': order.get('print_size'),
        'material': order.get('material'),
        'quantity': order.get('quantity', 1),
    }


def _format_price(price):
    """Format price as currency string."""
    if not price:
        return ""
    try:
        return f"${int(price):,}"
    except (ValueError, TypeError):
        return str(price)
