"""
Order Processing Service.

Handles the lifecycle of paid orders, including:
- Validating Stripe Payment status
- Updating Order Status
- Enabling Entitlements (Listing Unlock, SmartSign Activation)
- Triggering Fulfillment (Print Jobs, Listing Kits)

CANONICAL: Called ONLY from webhooks. Success pages are READ-ONLY and do not call this.
"""
import logging
import json
import stripe
from datetime import datetime
from database import get_db
from utils.timestamps import utc_iso
from services.stripe_checkout import update_attempt_status
from constants import (
    ORDER_STATUS_PAID, 
    ORDER_STATUS_SUBMITTED_TO_PRINTER, 
    ORDER_STATUS_FULFILLED
)

logger = logging.getLogger(__name__)

def resolve_user_id(db, session):
    """
    Resolve local User ID from Stripe Session using multiple strategies.
    1. metadata.user_id
    2. client_reference_id
    3. customer_email / customer_details.email
    """
    # 1. Metadata
    user_id = session.get('metadata', {}).get('user_id')
    if user_id: 
        return user_id
        
    # 2. Client Reference ID
    if session.get('client_reference_id'):
        return session.get('client_reference_id')

    # 3. Email Fallback
    email = session.get('customer_email')
    if not email and session.get('customer_details'):
        email = session.get('customer_details').get('email')
        
    if email:
        user = db.execute("SELECT id FROM users WHERE email = %s", (email,)).fetchone()
        if user:
            logger.info(f"[Orders] Resolved user {user['id']} via email match")
            return user['id']
            
    logger.warning(f"[Orders] Failed to resolve user for session {session.get('id')}")
    return None

def _parse_sign_asset_id(val):
    """
    Safely parse sign_asset_id from Stripe metadata.
    Returns int if valid string digit, None otherwise.
    """
    if not val:
        return None
    val_str = str(val).strip()
    if val_str.lower() in ('none', 'null', ''):
        return None
    if val_str.isdigit():
        return int(val_str)
    return None

def process_paid_order(db, session):
    """
    Process a successfully paid Stripe session.
    Idempotent: Can be called multiple times safely.
    
    Args:
        db: Database connection
        session: Stripe Session Object (dict)
    """
    session_id = session.get('id')
    order_id = session.get('metadata', {}).get('order_id')
    
    # Just in case, try client_reference_id if metadata missing
    if not order_id and session.get('client_reference_id'):
        order_id = session.get('client_reference_id')

    if not order_id:
        logger.error("[Orders] Error: No order_id in payment session")
        # Start a ValueError but don't crash app if called from route, return False?
        # Webhook expects 500 to retry, Route expects silent fail.
        # We'll raise to let caller handle logging/response.
        raise ValueError("No order_id in payment session metadata")

    logger.info(f"[Orders] Processing Paid Order {order_id} (Session: {session_id})")

    # Extract payment details
    shipping = session.get('shipping_details') or session.get('customer_details')
    shipping_json = json.dumps(shipping) if shipping else None
    customer_id = session.get('customer')  # Stripe customer ID
    
    # Define paid_at before SQL
    paid_at = utc_iso()
    
    # Fetch current order state to determine updates
    row = db.execute("SELECT status, order_type, property_id, user_id, design_payload FROM orders WHERE id = %s", (order_id,)).fetchone()
    if not row:
        logger.error(f"[Orders] Order {order_id} not found during processing")
        raise ValueError(f"Order {order_id} not found")
        
    current_status = row['status']
    current_type = row['order_type']
    
    # 1. Determine Correct Order Type (Canonical)
    purpose = session.get('metadata', {}).get('purpose')
    
    if purpose == 'listing_unlock':
        target_type = 'listing_unlock'
    elif purpose == 'listing_kit':
        target_type = 'listing_kit'
    elif purpose == 'smart_sign':
        target_type = 'smart_sign'
    else:
        # Default to existing type or 'sign' if unknown context
        target_type = 'sign'
    
    final_type = current_type
    if current_type == 'yard_sign':
        final_type = 'sign'
    elif current_type not in ('sign', 'listing_unlock', 'smart_sign', 'listing_kit'):
        final_type = target_type
        
    # 2. Prevent Status Regression & Idempotency Check
    # If already fully processed (submitted/fulfilled), do NOT set back to 'paid'
    new_status = ORDER_STATUS_PAID
    if current_status in (ORDER_STATUS_SUBMITTED_TO_PRINTER, ORDER_STATUS_FULFILLED):
        new_status = current_status
        logger.info(f"[Orders] Order {order_id} is already {current_status}. Preserving status.")
    elif current_status == ORDER_STATUS_PAID:
        logger.info(f"[Orders] Order {order_id} is already PAID. Checking logic for missing steps (Redundancy).")
    
    logger.info(f"[Orders] Updating Order {order_id}: Status {current_status}->{new_status}, Type {current_type}->{final_type}")
    
    # --- STRICT PAYMENT CHECK ---
    # Only activate/fulfill if definitive paid status
    payment_status = session.get('payment_status')
    if payment_status != 'paid':
        logger.warning(f"[Orders] Session {session_id} payment_status={payment_status}. Skipping activation/fulfillment.")
        return

    # Update order with payment information + fixed type + status
    db.execute('''
        UPDATE orders 
        SET status = %s, 
            order_type = %s,
            stripe_checkout_session_id = %s, 
            stripe_payment_intent_id = %s, 
            stripe_customer_id = %s,
            paid_at = %s, 
            shipping_address = %s,
            amount_total_cents = %s,
            currency = %s
        WHERE id = %s
    ''', (
        new_status,
        final_type,
        session_id, 
        session.get('payment_intent'), 
        customer_id, 
        paid_at, 
        shipping_json, 
        session.get('amount_total'),  # Capture raw cents
        session.get('currency'),      # Capture currency code
        order_id
    ))
    db.commit()
    
    # Mark checkout attempt as completed (if present)
    attempt_token = session.get("metadata", {}).get("attempt_token")
    if attempt_token:
        try:
            update_attempt_status(attempt_token, "completed", stripe_customer_id=customer_id)
            logger.info(f"[Orders] Marked attempt {attempt_token} as completed")
        except Exception as e:
            logger.warning(f"[Orders] Could not update attempt {attempt_token}: {e}")

    # 3. Universal Entitlement Unlock
    raw_property_id = session.get('metadata', {}).get('property_id')
    property_id = None

    if isinstance(raw_property_id, int) and raw_property_id > 0:
        property_id = raw_property_id
    elif isinstance(raw_property_id, str):
        s = raw_property_id.strip()
        if s.isdigit():
            property_id = int(s)

    if not property_id:
        try:
            if row and row['property_id'] is not None:
                property_id = int(row['property_id'])
        except Exception:
            property_id = None

    if property_id:
        if final_type in ('sign', 'listing_unlock', 'smart_sign'):
            db.execute("UPDATE properties SET expires_at = NULL WHERE id = %s", (property_id,))
            db.commit()
            logger.info(f"[Orders] Property {property_id} unlocked for Order {order_id} (expires_at=NULL).")

    # 4. SmartSign Creation & Activation (Idempotent)
    if final_type == 'smart_sign':
        raw_asset_id = session.get('metadata', {}).get('sign_asset_id')
        asset_id = _parse_sign_asset_id(raw_asset_id)
        
        # If no asset_id, create one
        if not asset_id:
            # Check for existing asset by activation_order_id (Idempotency)
            existing_asset = db.execute(
                "SELECT id FROM sign_assets WHERE activation_order_id = %s", 
                (order_id,)
            ).fetchone()
            
            if existing_asset:
                asset_id = existing_asset['id']
                logger.info(f"[Orders] Found existing asset {asset_id} for Order {order_id}")
            else:
                user_id = row['user_id']
                if not user_id:
                     user_id = resolve_user_id(db, session)

                payload = row.get('design_payload') or {}
                if isinstance(payload, str):
                    payload = json.loads(payload)
                    
                code = payload.get('code')
                if not code:
                     from utils.qr_codes import generate_unique_code
                     code = generate_unique_code(db, length=12)
                     logger.warning(f"[Orders] Warning: Code missing in payload for Order {order_id}. Generated new {code}.")
                
                brand_name = payload.get('brand_name') or payload.get('agent_name')
                phone = payload.get('phone') or payload.get('agent_phone')
                email_addr = payload.get('email') or payload.get('agent_email')
                bg_style = payload.get('background_style') or payload.get('banner_color_id') or 'solid_blue'
                
                inc_logo = bool(payload.get('logo_key') or payload.get('agent_logo_key'))
                logo_key = payload.get('logo_key') or payload.get('agent_logo_key')
                inc_head = bool(payload.get('headshot_key') or payload.get('agent_headshot_key'))
                headshot_key = payload.get('headshot_key') or payload.get('agent_headshot_key')
                
                label = f"SmartSign {code}"
                
                # V2 Fields (Phase 2 Persistence)
                agent_name = payload.get('agent_name') or payload.get('brand_name')
                agent_phone = payload.get('agent_phone') or payload.get('phone')
                # Safer state handling: defaults to NULL if empty string
                _state_raw = (payload.get('state') or '').strip().upper()
                state = _state_raw[:2] if _state_raw else None
                
                _lic_raw = (payload.get('license_number') or '').strip()
                license_number = _lic_raw if _lic_raw else None
                
                show_license_option = payload.get('show_license_option') or 'auto'
                
                _lic_label = (payload.get('license_label_override') or '').strip()
                license_label_override = _lic_label if _lic_label else None
                
                # Create Activated Asset
                res = db.execute("""
                    INSERT INTO sign_assets (
                        user_id, code, brand_name, phone, email,
                        background_style, cta_key,
                        include_logo, logo_key,
                        include_headshot, headshot_key,
                        agent_name, agent_phone, state, license_number, show_license_option, license_label_override,
                        created_at, activated_at, is_frozen, activation_order_id, label
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, 'scan_for_details', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW(), FALSE, %s, %s)
                    RETURNING id
                """, (
                    user_id, code, brand_name, phone, email_addr,
                    bg_style, 
                    inc_logo, logo_key,
                    inc_head, headshot_key,
                    agent_name, agent_phone, state, license_number, show_license_option, license_label_override,
                    order_id, label
                )).fetchone()
                
                asset_id = res['id']
                db.commit()
                logger.info(f"[Orders] Created NEW Asset {asset_id} ({code}) for Order {order_id}")
                
                # Link Asset to Order
                db.execute("UPDATE orders SET sign_asset_id = %s WHERE id = %s", (asset_id, order_id))
                db.commit()

        # If asset exists (legacy/re-order/just created), ensure activated
        if asset_id:
            existing = db.execute("SELECT activated_at FROM sign_assets WHERE id = %s", (asset_id,)).fetchone()
            if existing and existing['activated_at'] is None:
                db.execute("""
                    UPDATE sign_assets 
                    SET activated_at = CURRENT_TIMESTAMP,
                        activation_order_id = %s
                    WHERE id = %s
                """, (order_id, asset_id))
                db.commit()
                logger.info(f"[Orders] Activated SmartSign Asset {asset_id} for Order {order_id}")
            else:
                logger.info(f"[Orders] Asset {asset_id} already activated. Skipping.")

    # 5. Trigger Fulfillment (Async)
    if final_type in ('sign', 'smart_sign'):
        # Check if job exists (Idempotent)
        existing_job = db.execute("SELECT job_id FROM print_jobs WHERE order_id = %s", (order_id,)).fetchone()
        
        if existing_job:
            logger.info(f"[Orders] Print job already exists for Order {order_id}. Skipping queue.")
        else:
            logger.info(f"[Orders] Enqueuing fulfillment for Sign Order {order_id}...")
            from services.async_jobs import enqueue
            job_id = enqueue('fulfill_order', {'order_id': order_id})
            logger.info(f"[Orders] Enqueued Job {job_id}")

    elif final_type == 'listing_kit':
        # Trigger Listing Kit Generation (Async)
        logger.info(f"[Orders] Enqueuing Listing Kit generation for Order {order_id}...")
        from services.async_jobs import enqueue
        job_id = enqueue('generate_listing_kit', {'order_id': order_id})
        logger.info(f"[Orders] Enqueued Job {job_id}")
