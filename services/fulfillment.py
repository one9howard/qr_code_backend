import os
import requests
import time
from database import get_db
from config import PRINT_JOBS_TOKEN
from utils.timestamps import utc_iso
from services.pdf_smartsign import generate_smartsign_pdf
from constants import (
    ORDER_STATUS_PENDING_PAYMENT, 
    ORDER_STATUS_PAID, 
    ORDER_STATUS_SUBMITTED_TO_PRINTER,
    ORDER_STATUS_PRINT_FAILED,
    ORDER_STATUS_FULFILLED,  # Reserved for future
    SIGN_SIZES,
    SIGN_COLORS,
    DEFAULT_SIGN_SIZE,
    DEFAULT_SIGN_COLOR
)

def validate_sign_options(order, order_id):
    """
    Validate sign_size and sign_color from order, using defaults if invalid.
    Returns tuple: (validated_size, validated_color)
    """
    sign_size = order['sign_size'] if order['sign_size'] else DEFAULT_SIGN_SIZE
    sign_color = order['sign_color'] if order['sign_color'] else DEFAULT_SIGN_COLOR
    
    # Validate sign_size against allowed presets
    if sign_size not in SIGN_SIZES:
        print(f"[Fulfillment] WARNING: Order {order_id} has invalid sign_size '{sign_size}'. Using default '{DEFAULT_SIGN_SIZE}'.")
        sign_size = DEFAULT_SIGN_SIZE
    
    # Validate sign_color - must be a valid hex color
    import re
    if not re.match(r'^#[0-9a-fA-F]{6}$', sign_color):
        print(f"[Fulfillment] WARNING: Order {order_id} has invalid sign_color '{sign_color}'. Using default '{DEFAULT_SIGN_COLOR}'.")
        sign_color = DEFAULT_SIGN_COLOR
    
    return sign_size, sign_color

def fulfill_order(order_id):
    """
    Idempotently fulfill an order by sending the PDF to the print server.
    Only proceeds if order is paid and not yet submitted.
    
    Returns:
        bool: True if successful (or already fulfilled), False on failure
    """
    db = get_db()
    
    # 1. Fetch Order
    order = db.execute("SELECT * FROM orders WHERE id = %s", (order_id,)).fetchone()
    if not order:
        print(f"[Fulfillment] Error: Order {order_id} not found.")
        return False

    # 2. Idempotency & Safety Check
    # If already submitted successfully, return True (idempotent)
    if order['submitted_at']:
        print(f"[Fulfillment] Order {order_id} already submitted at {order['submitted_at']}.")
        return True
        
    # Only fulfill if status is 'paid' and not yet submitted
    if order['status'] != ORDER_STATUS_PAID:
        print(f"[Fulfillment] Blocked: Order {order_id} is in status '{order['status']}', not '{ORDER_STATUS_PAID}'.")
        return False

    # --- LAYERED SAFETY: STRICT TYPE CHECK ---
    # Only 'sign' orders should ever reach the printer.
    # 'listing_unlock' or others should be NO-OPs here.
    # Use dict() to ensure .get() works for DictRow
    order_type = dict(order).get('order_type')
    if order_type not in ('sign', 'smart_sign'):
        print(f"[Fulfillment] NO-OP: Order {order_id} is type '{order_type}', not 'sign' or 'smart_sign'. Skipping print job.")
        # Return True so calling processes (webhooks) consider it "handled" and don't retry.
        return True

    # Phase 5: Productized Generation
    # If an order is productized, we (re)generate the print-grade PDF at fulfillment time
    # so SKU choices (e.g., double-sided) are always honored, even if a preview PDF already exists.
    print_product = dict(order).get('print_product')
    if print_product:
        print(f"[Fulfillment] Generating PDF for SKU {print_product} Order {order_id}...")
        try:
             import io
             from services.print_catalog import validate_sku

             # Normalize defaults
             order_map = dict(order)
             material = order_map.get('material') or ('coroplast_4mm' if print_product == 'listing_sign' else 'aluminum_040')
             sides = order_map.get('sides') or 'single'
             order_map['material'] = material
             order_map['sides'] = sides

             ok, reason = validate_sku(print_product, material, sides)
             if not ok:
                 raise ValueError(f"Invalid SKU: {reason}")

             pdf_bytes = None
             if print_product == 'listing_sign':
                 from services.printing.listing_sign import generate_listing_sign_pdf
                 pdf_bytes = generate_listing_sign_pdf(db, order_map)
             elif print_product == 'smart_sign':
                 from services.printing.smart_sign import generate_smart_sign_pdf
                 pdf_bytes = generate_smart_sign_pdf(db, order_map)
             else:
                 raise ValueError(f"Unknown print_product: {print_product}")

             # Save to Storage
             from utils.storage import get_storage
             key = f"pdfs/order_{order_id}/{print_product}_{int(time.time())}.pdf"
             storage = get_storage()
             storage.put_file(io.BytesIO(pdf_bytes), key, content_type='application/pdf')
             
             db.execute("UPDATE orders SET sign_pdf_path = %s WHERE id = %s", (key, order_id))
             db.commit()
             # Refresh map
             order = db.execute("SELECT * FROM orders WHERE id = %s", (order_id,)).fetchone()

        except Exception as e:
             err = f"Generator Failed: {str(e)}"
             print(f"[Fulfillment] {err}")
             db.execute("UPDATE orders SET status=%s, fulfillment_error=%s WHERE id=%s", 
                        (ORDER_STATUS_PRINT_FAILED, err, order_id))
             db.commit()
             return False

    # SmartSign PDF Generation (Legacy Fallback)
    if not print_product and order_type == 'smart_sign' and not order['sign_pdf_path']:
        print(f"[Fulfillment] Generating PDF for SmartSign Order {order_id}...")
        try:
            asset_id = order['sign_asset_id']
            # Fetch asset
            asset = db.execute("SELECT * FROM sign_assets WHERE id = %s", (asset_id,)).fetchone()
            if not asset:
                raise ValueError(f"Asset {asset_id} not found")
                
            # from services.pdf_smartsign import generate_smartsign_pdf <-- Moved to top
            # Generate and save
            pdf_key = generate_smartsign_pdf(asset, order_id=order_id)
            
            # Update order
            db.execute("UPDATE orders SET sign_pdf_path = %s WHERE id = %s", (pdf_key, order_id))
            db.commit()
            
            # Update local order object ref for next steps
            order = db.execute("SELECT * FROM orders WHERE id = %s", (order_id,)).fetchone()
            
        except Exception as e:
            error_msg = f"SmartSign PDF Generation Failed: {str(e)}"
            print(f"[Fulfillment] {error_msg}")
            db.execute(
                "UPDATE orders SET status = %s, fulfillment_error = %s WHERE id = %s",
                (ORDER_STATUS_PRINT_FAILED, error_msg, order_id)
            )
            db.commit()
            return False

    # 3. Get PDF from Storage (S3 or Local)
    pdf_key = order['sign_pdf_path']
    if not pdf_key:
        print(f"[Fulfillment] Error: Order {order_id} has no PDF path.")
        error_msg = "Missing PDF file path"
        db.execute(
            "UPDATE orders SET status = %s, fulfillment_error = %s WHERE id = %s",
            (ORDER_STATUS_PRINT_FAILED, error_msg, order_id)
        )
        db.commit()
        return False

    # Use storage abstraction to check if PDF exists
    from utils.storage import get_storage
    storage = get_storage()
    
    if not storage.exists(pdf_key):
        print(f"[Fulfillment] Error: PDF file not found for order {order_id}. Storage key: {pdf_key}")
        error_msg = f"PDF file not found in storage: {pdf_key}"
        db.execute(
            "UPDATE orders SET status = %s, fulfillment_error = %s WHERE id = %s",
            (ORDER_STATUS_PRINT_FAILED, error_msg, order_id)
        )
        db.commit()
        return False

    # 4. Validate and prepare sign options
    sign_size, sign_color = validate_sign_options(order, order_id)

    # 5. Select Provider & Submit
    # Default to 'internal' if not set
    provider_name = os.environ.get('FULFILLMENT_PROVIDER', 'internal')
    
    try:
        if provider_name == 'printful':
             from services.fulfillment_providers.printful import PrintfulProvider
             provider = PrintfulProvider()
        else:
             from services.fulfillment_providers.internal import InternalQueueProvider
             provider = InternalQueueProvider()
             
        # Prepare shipping data
        import json
        shipping_data = json.loads(order['shipping_address']) if order['shipping_address'] else {}
        
        # Submit to provider
        # Provider handles file transfer/storage and internal queue/API calls
        provider_job_id = provider.submit_order(order_id, shipping_data, pdf_key)
        
        # 6. Update Order Status
        # Idempotency key for the PRINT JOB (not the Stripe payment)
        print_idempotency_key = f"order_{order_id}"
        
        submitted_at = utc_iso()
        db.execute('''
            UPDATE orders 
            SET status = %s, 
                submitted_at = %s, 
                provider_job_id = %s,
                print_idempotency_key = %s,
                fulfillment_error = NULL
            WHERE id = %s
        ''', (ORDER_STATUS_SUBMITTED_TO_PRINTER, submitted_at, provider_job_id, print_idempotency_key, order_id))
        
        db.commit()
        print(f"[Fulfillment] Success: Order {order_id} submitted to {provider_name} (job_id={provider_job_id})")
        return True

    except Exception as e:
        error_msg = f"Exception during fulfillment ({provider_name}): {str(e)}"
        print(f"[Fulfillment] {error_msg}")
        # We try to record the error in the order
        try:
            db.execute(
                "UPDATE orders SET status = %s, fulfillment_error = %s WHERE id = %s",
                (ORDER_STATUS_PRINT_FAILED, error_msg, order_id)
            )
            db.commit()
        except:
            pass
        return False
