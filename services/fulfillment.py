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
    
    # STRICT IDEMPOTENCY CHECK
    # Always check if a print_job already exists for this order, regardless of status.
    idempotency_key = f"order_{order_id}"
    existing_job = db.execute(
        "SELECT job_id FROM print_jobs WHERE idempotency_key = %s",
        (idempotency_key,)
    ).fetchone()
    
    if existing_job:
        print(f"[Fulfillment] Idempotency hit: Print job {existing_job['job_id']} already exists for order {order_id}")
        # Ensure order status is consistent
        if status != 'submitted_to_printer':
             db.execute(
                "UPDATE orders SET status = 'submitted_to_printer', provider_job_id = %s, updated_at = NOW() WHERE id = %s",
                (existing_job['job_id'], order_id)
             )
             db.commit()
        return True

    if status == 'submitted_to_printer':
        # If we are here, no print_job was found (maybe manual DB update?), but status says submitted.
        # We should proceed to re-submit or fail?
        # Safe bet: Retry submission if job is missing.
        print(f"[Fulfillment] Order {order_id} is 'submitted_to_printer' but no job found. Retrying.")
    
    
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
        
    elif (print_product and print_product.startswith('listing_sign')) or order_type == 'sign':
        pdf_key = _generate_listing_sign_pdf(db, order, storage)
        
    elif print_product == 'smart_riser':
        pdf_key = _generate_smart_riser_pdf(db, order, storage)
        
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
    
    # Inject Order Context (Print Size, Layout) into Asset for Generator
    # Convert Row to dict if needed
    if not isinstance(asset, dict):
        asset = dict(asset)
        
    asset['print_size'] = order.get('print_size')
    asset['layout_id'] = order.get('layout_id')
    
    # --- Compatibility Safety Net (P0) ---
    # Merge payload into asset only when DB fields are missing.
    # This supports orders created before migration or if DB load failed to capture fields.
    if not asset.get('agent_name'):
         payload = order.get('design_payload') or {}
         if isinstance(payload, str):
             import json
             try: payload = json.loads(payload)
             except: payload = {}
             
         if payload.get('agent_name'):
             asset['agent_name'] = payload.get('agent_name')
         if payload.get('agent_phone'):
             asset['agent_phone'] = payload.get('agent_phone')
         
         # Also merge license fields if missing
         if not asset.get('state') and payload.get('state'):
              asset['state'] = payload.get('state')
         if not asset.get('license_number') and payload.get('license_number'):
              asset['license_number'] = payload.get('license_number')
         if not asset.get('show_license_option') and payload.get('show_license_option'):
              asset['show_license_option'] = payload.get('show_license_option')
         if not asset.get('license_label_override') and payload.get('license_label_override'):
              asset['license_label_override'] = payload.get('license_label_override')
    
    
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
    # STRICT: Delegate to canonical unified wrapper
    from services.printing.listing_sign import generate_listing_sign_pdf_from_order_row
    
    try:
        # Convert to dict if needed
        if hasattr(order, '_asdict'):
            order_row = order._asdict()
        elif not isinstance(order, dict):
            order_row = dict(order)
        else:
            order_row = order
            
        # Use unified wrapper
        pdf_key = generate_listing_sign_pdf_from_order_row(order_row, storage=storage, db=db)
        print(f"[Fulfillment] Generated listing sign PDF: {pdf_key}")
        return pdf_key
    except Exception as e:
        logger.error(f"[Fulfillment] Listing sign PDF generation failed: {e}")
        return None


def _generate_smart_riser_pdf(db, order, storage):
    """Generate SmartRiser PDF."""
    from services.printing.smart_riser import generate_smart_riser_pdf
    
    try:
        pdf_key = generate_smart_riser_pdf(order)
        print(f"[Fulfillment] Generated SmartRiser PDF: {pdf_key}")
        return pdf_key
    except Exception as e:
        logger.error(f"[Fulfillment] SmartRiser PDF generation failed: {e}")
        return None


def _build_shipping_data(db, order):
    """Build shipping metadata for print job."""
    user_id = order['user_id']
    
    # Load user fallback
    user = db.execute(
        "SELECT * FROM users WHERE id = %s", (user_id,)
    ).fetchone()

    # Parse proper shipping address from Stripe JSON
    # order['shipping_address'] is just string/json field in DB (jsonb or text)
    # psycopg2.extras.Json adapter handles serialization, but reading back? 
    # It might be a dict or string depending on DB driver. 
    # If using RealDictCursor, it handles JSON types usually.
    
    shipping_payload = order.get('shipping_address')
    address_line = None
    city = None
    state = None
    postal_code = None
    recipient_name = None
    
    if shipping_payload:
        if isinstance(shipping_payload, str):
            import json
            try:
                shipping_payload = json.loads(shipping_payload)
            except: pass
            
        if isinstance(shipping_payload, dict):
            # Stripe format: { 'name': '...', 'address': { 'line1': ... } }
            recipient_name = shipping_payload.get('name')
            addr = shipping_payload.get('address') or {}
            address_line = addr.get('line1')
            if addr.get('line2'):
                address_line += f", {addr.get('line2')}"
            city = addr.get('city')
            state = addr.get('state')
            postal_code = addr.get('postal_code')

    # If no shipping from order, maybe user profile? (Phase 1)
    
    return {
        'order_id': order['id'],
        'order_type': order['order_type'],
        'user_id': user_id,
        'user_email': user.get('email') if user else None,
        'print_size': order.get('print_size'),
        'material': order.get('material'),
        'quantity': order.get('quantity', 1),
        'shipping_name': recipient_name or (user.get('full_name') if user else 'Valued Customer'),
        'shipping_address': address_line,
        'shipping_city': city,
        'shipping_state': state,
        'shipping_zip': postal_code
    }


def _format_price(price):
    """Format price as currency string."""
    if not price:
        return ""
    try:
        return f"${int(price):,}"
    except (ValueError, TypeError):
        return str(price)
