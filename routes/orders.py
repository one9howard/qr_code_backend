import os
import time
import stripe
import traceback
import io

from flask import Blueprint, request, jsonify, current_app, render_template, redirect, url_for, flash, session, send_file, abort
from flask_login import login_required, current_user
from database import get_db, get_agent_data_for_order
from config import (
    STRIPE_SECRET_KEY, STRIPE_PRICE_SIGN, STRIPE_SIGN_SUCCESS_URL, STRIPE_SIGN_CANCEL_URL
)
from services.stripe_checkout import (
    create_checkout_attempt,
    get_latest_attempt_for_order,
    update_attempt_status,
    validate_attempt_params,
    compute_params_hash
)
from utils.sign_options import normalize_sign_size
from services.stripe_prices import get_price_id_for_size
from constants import (
    SIGN_SIZES, DEFAULT_SIGN_SIZE,
    ORDER_STATUS_PENDING_PAYMENT, ORDER_STATUS_PAID,
    ORDER_STATUS_SUBMITTED_TO_PRINTER, ORDER_STATUS_FULFILLED,
    LAYOUT_VERSION, PAID_STATUSES
)
from utils.storage import get_storage
from utils.filenames import make_sign_asset_basename

orders_bp = Blueprint('orders', __name__)

# Status values that lock an order from modification
LOCKED_STATUSES = {ORDER_STATUS_PAID, ORDER_STATUS_SUBMITTED_TO_PRINTER, ORDER_STATUS_FULFILLED}


@orders_bp.route("/orders/<int:order_id>/download-pdf")
def download_pdf(order_id):
    """
    PDF download route - DISABLED.
    Always returns 404 to prevent direct PDF downloads.
    """
    abort(404, description="This PDF is no longer available")


@orders_bp.route("/orders/<int:order_id>/preview")
def order_preview(order_id):
    """
    Serve preview image with authorization.
    """
    db = get_db()
    order = db.execute("SELECT * FROM orders WHERE id = %s", (order_id,)).fetchone()
    
    if not order:
        abort(404, description="Order not found")
    
    # Authorization check
    authorized = False
    
    if current_user.is_authenticated:
        if order['user_id'] == current_user.id:
            authorized = True
    else:
        guest_token = request.args.get('guest_token')
        if guest_token:
            session_tokens = session.get('guest_tokens', [])
            if guest_token in session_tokens and order['guest_token'] == guest_token:
                authorized = True
    
    if not authorized:
        abort(403, description="Not authorized to view this preview")
    
    # Generate expected preview key
    # Previews are stored in "previews/order_{id}/basename.webp"
    sign_size = normalize_sign_size(order['sign_size'])
    basename = make_sign_asset_basename(order_id, sign_size)
    preview_key = f"previews/order_{order_id}/{basename}.webp"
    
    storage = get_storage()
    
    if not storage.exists(preview_key):
        abort(404, description="Preview not found")
    
    try:
        # Get URL or bytes
        # For preview images, a public/presigned URL is best if backend supports it
        # But send_file allows us to control caching and headers better
        file_bytes = storage.get_file(preview_key)
        
        return send_file(
            file_bytes,
            mimetype="image/webp",
            conditional=True,
            max_age=60  # 1 minute cache
        )
    except Exception as e:
        current_app.logger.error(f"Error serving preview: {e}")
        abort(500)


@orders_bp.route("/order-sign", methods=["POST"])
def order_sign():
    """
    Create Stripe Checkout Session for Sign Order.
    """
    # ... logic identical to before, just DB reads ...
    # 1. Receive data
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "No data provided"}), 400
    
    order_id = data.get("order_id")
    guest_token = data.get("guest_token")
    property_id = data.get("property_id")
    
    if not order_id and not property_id:
        return jsonify({"success": False, "error": "Missing order_id"}), 400

    db = get_db()
    stripe.api_key = STRIPE_SECRET_KEY
    
    # 2. Authorization & Order Lookup
    order = None
    
    if current_user.is_authenticated:
        if order_id:
            order = db.execute("SELECT * FROM orders WHERE id = %s AND user_id = %s", (order_id, current_user.id)).fetchone()
        else:
            order = db.execute("SELECT * FROM orders WHERE property_id = %s AND user_id = %s", (property_id, current_user.id)).fetchone()
    else:
        if not guest_token:
            return jsonify({"success": False, "error": "Missing guest_token for checkout"}), 403
        
        guest_tokens = session.get('guest_tokens', [])
        if guest_token not in guest_tokens:
            return jsonify({"success": False, "error": "Invalid or expired guest session. Please regenerate your sign."}), 403
        
        order = db.execute(
            "SELECT * FROM orders WHERE id = %s AND guest_token = %s", 
            (order_id, guest_token)
        ).fetchone()
        
    if not order:
        return jsonify({"success": False, "error": "Order record not found"}), 404
        
    if not order['sign_pdf_path']:
        return jsonify({"success": False, "error": "No generated sign found for this order"}), 404

    # 3. Build checkout params
    customer_email = None
    if current_user.is_authenticated:
        customer_email = current_user.email
    elif order['guest_email']:
        customer_email = order['guest_email']
        
    user_id_val = current_user.id if current_user.is_authenticated else None
    is_guest = not current_user.is_authenticated

    raw_sign_size = order['sign_size']
    sign_size = normalize_sign_size(raw_sign_size)
    
    # Phase 5: Strict SKU & Pricing
    # 1. Read Material/Sides from request
    material = request.get_json().get('material', 'coroplast_4mm')
    sides = request.get_json().get('sides', 'single')
    
    # 2. Validate SKU
    from services.print_catalog import validate_sku, get_price_id
    ok, reason = validate_sku('listing_sign', material, sides)
    if not ok:
        return jsonify({"success": False, "error": f"Invalid SKU: {reason}"}), 400
        
    # 3. Get Strict Price ID
    try:
        price_id = get_price_id('listing_sign', material, sides)
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
        
    # 4. Update Order with SKU Spec
    db.execute("""
        UPDATE orders 
        SET print_product='listing_sign', material=%s, sides=%s 
        WHERE id=%s
    """, (material, sides, order['id']))
    db.commit()
    
    # Legacy lookup key (optional, can be empty string if not used by Stripe anymore)
    lookup_key = ""
    
    checkout_params = {
        'line_items': [{'price': price_id, 'quantity': 1}],
        'mode': 'payment',
        'success_url': STRIPE_SIGN_SUCCESS_URL,
        'cancel_url': STRIPE_SIGN_CANCEL_URL,
        'customer_email': customer_email,
        'client_reference_id': str(order['id']),
        'shipping_address_collection': {'allowed_countries': ['US']},
        'metadata': {
            'order_id': str(order['id']),
            'property_id': str(order['property_id']),
            'user_id': str(user_id_val) if user_id_val else '',
            'is_guest': 'true' if is_guest else 'false',
            'purpose': 'sign_order',
            'sign_size': sign_size,
            'sign_lookup_key': lookup_key if lookup_key else ''
        }
    }

    try:
        attempt = None
        existing_attempt = get_latest_attempt_for_order(order['id'], 'sign_order')
        
        if existing_attempt and existing_attempt.get('stripe_session_id'):
            try:
                existing_session = stripe.checkout.Session.retrieve(
                    existing_attempt['stripe_session_id']
                )
                if existing_session.status == 'open':
                    if validate_attempt_params(existing_attempt, checkout_params):
                        return jsonify({"success": True, "checkoutUrl": existing_session.url})
            except stripe.error.InvalidRequestError:
                pass

        attempt = create_checkout_attempt(
            user_id=user_id_val,
            purpose='sign_order',
            params=checkout_params,
            order_id=order['id']
        )
        
        checkout_params['metadata']['attempt_token'] = attempt['attempt_token']
        
        checkout_session = stripe.checkout.Session.create(
            **checkout_params,
            idempotency_key=attempt['idempotency_key']
        )
        
        update_attempt_status(
            attempt['attempt_token'],
            'session_created',
            stripe_session_id=checkout_session.id
        )
        
        db.execute("UPDATE orders SET stripe_checkout_session_id = %s WHERE id = %s", (checkout_session.id, order['id']))
        db.commit()

        return jsonify({"success": True, "checkoutUrl": checkout_session.url})
        
    except stripe.error.StripeError as e:
        err_msg = str(e)
        current_app.logger.error(f"[Orders] Stripe error: {err_msg}")
        
        # Check for price errors specifically to help user diagnose
        if "No such price" in err_msg or "No such plan" in err_msg:
             return jsonify({
                 "success": False, 
                 "error": "configuration_error",
                 "message": f"Pricing configuration error: {err_msg}. Please check Stripe Price IDs in Railway variables."
             }), 400
             
        return jsonify({"success": False, "error": err_msg}), 400
        
    except Exception as e:
        current_app.logger.error(f"[Orders] Checkout error: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@orders_bp.route("/orders/start/<int:property_id>")
@login_required
def order_sign_start(property_id):
    """
    Dashboard entry point for ordering a sign.
    """
    db = get_db()
    
    # 1. Verify property ownership
    property_row = db.execute("""
        SELECT p.* 
        FROM properties p
        JOIN agents a ON p.agent_id = a.id
        WHERE p.id = %s AND a.user_id = %s
    """, (property_id, current_user.id)).fetchone()
    
    if not property_row:
        flash("Property not found or access denied.", "error")
        return redirect(url_for('dashboard.index'))
        
    # 2. Find most recent valid order with a generated sign
    # Prefer 'sign' type, tie-break with recency
    order = db.execute("""
        SELECT * FROM orders 
        WHERE property_id = %s AND sign_pdf_path IS NOT NULL
        ORDER BY CASE WHEN order_type='sign' THEN 1 ELSE 2 END ASC, created_at DESC
        LIMIT 1
    """, (property_id,)).fetchone()
    
    if not order:
        flash("Please generate a sign design first.", "warning")
        return redirect(url_for('dashboard.index'))
        
    # 3. Prepare context for assets.html
    order_id = order['id']
    sign_size = order['sign_size']
    status = order['status']
    is_locked = status in LOCKED_STATUSES
    
    preview_url = url_for('orders.order_preview', order_id=order_id)
    # Add timestamp for cache busting
    timestamp = int(time.time())
    preview_url += f"?v={timestamp}"
    
    # Property public URL
    property_url = url_for('properties.property_page', slug=property_row['slug'], _external=True)

    # Render assets page (which serves as the "Order Sign" dashboard view)
    return render_template(
        "assets.html",
        order_id=order_id,
        guest_token='', # Logged in user doesn't need guest token
        order_status=status,
        is_locked=is_locked,
        preview_url=preview_url,
        property_url=property_url,
        sign_size=sign_size,
        timestamp=timestamp,
        property=property_row # Pass property object too just in case template needs it
    )


@orders_bp.route("/order/success")
def success():
    """
    Render-only confirmation page.
    Does NOT mutate state. All processing is done via Webhook.
    """
    session_id = request.args.get('session_id')
    
    # Optional: Retrieve session to show details, but DO NOT update DB.
    if session_id:
        try:
             # Just verify it exists/fetch display info if needed
             # For now, just render the template.
             pass
        except Exception as e:
            current_app.logger.warning(f"[Orders] Success page error (display only): {e}")

    return render_template("order_success.html", session_id=session_id)


@orders_bp.route("/order/cancel")
def cancel():
    flash("Sign order cancelled.", "info")
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    else:
        return redirect(url_for('agent.submit'))


@orders_bp.route("/api/orders/<int:order_id>/resize", methods=["POST"])
def resize_order(order_id):
    """
    Regenerate PDF + preview for a new size.
    """
    from utils.pdf_generator import generate_pdf_sign
    from utils.pdf_preview import render_pdf_to_web_preview

    data = request.get_json() or {}
    new_size = data.get("size")
    guest_token = data.get("guest_token")
    
    # Validate size
    normalized_size = normalize_sign_size(new_size)
    if normalized_size not in SIGN_SIZES:
        return jsonify({
            "success": False,
            "error": "invalid_size",
            "message": f"Invalid size '{new_size}'"
        }), 400
    
    db = get_db()
    
    # Fetch order
    order = db.execute("SELECT * FROM orders WHERE id = %s", (order_id,)).fetchone()
    if not order:
        return jsonify({"success": False, "error": "not_found", "message": "Order not found"}), 404
    
    # Authorization check
    authorized = False
    if current_user.is_authenticated:
        if order['user_id'] == current_user.id:
            authorized = True
    else:
        if guest_token and order['guest_token'] == guest_token:
            session_tokens = session.get('guest_tokens', [])
            if guest_token in session_tokens:
                authorized = True
    
    if not authorized:
        return jsonify({"success": False, "error": "unauthorized", "message": "Unauthorized"}), 403
    
    # Check if order is locked
    if order['status'] in LOCKED_STATUSES:
        return jsonify({"success": False, "error": "order_locked_paid", "message": "Cannot resize paid order"}), 400
    
    # If size hasn't changed
    current_size = normalize_sign_size(order['sign_size'])
    if normalized_size == current_size:
        preview_url = url_for('orders.order_preview', order_id=order_id)
        if guest_token:
            preview_url += f'?guest_token={guest_token}'
        return jsonify({
            "success": True,
            "size": normalized_size,
            "pdf_url": url_for('orders.download_pdf', order_id=order_id),
            "preview_url": preview_url,
            "message": "Size unchanged"
        })
    
    # Store old PDF key for cleanup
    old_pdf_key = order['sign_pdf_path']
    
    try:
        property_row = db.execute(
            "SELECT * FROM properties WHERE id = %s",
            (order['property_id'],)
        ).fetchone()
        
        if not property_row:
            return jsonify({"success": False, "error": "render_failed", "message": "Property data not found"}), 500
        
        property_data = dict(property_row)
        
        agent_data = get_agent_data_for_order(order_id)
        if not agent_data:
            agent_data = db.execute(
                "SELECT name, brokerage, email, phone, photo_filename FROM agents WHERE id = %s",
                (property_data['agent_id'],)
            ).fetchone()
            if agent_data:
                agent_data = dict(agent_data)
        
        if not agent_data:
            return jsonify({"success": False, "error": "render_failed", "message": "Agent data not found"}), 500
        
        # Resolve agent photo key
        agent_photo_key = agent_data.get('photo_filename')
        # Check if key exists in storage to be safe?
        storage = get_storage()
        if agent_photo_key and not storage.exists(agent_photo_key):
             agent_photo_key = None

        # Get QR code val
        qr_code_value = property_data.get('qr_code')
        if not qr_code_value:
             return jsonify({"success": False, "error": "render_failed", "message": "No QR Code"}), 500
        
        # We need a QR key if we want raster fallback, but we prefer vector URL
        # We can reconstruct path if needed or just rely on vector.
        # But `generate_pdf_sign` asks for `qr_key`.
        # We can construct expected key: `qr/{qr_code}.png`
        qr_key = f"qr/{qr_code_value}.png"
        
        from config import BASE_URL
        qr_value = f"{BASE_URL}/r/{qr_code_value}"
        
        new_pdf_key = generate_pdf_sign(
            address=property_data['address'],
            beds=property_data['beds'],
            baths=property_data['baths'],
            sqft=property_data.get('sqft', ''),
            price=property_data.get('price', ''),
            agent_name=agent_data['name'],
            brokerage=agent_data['brokerage'],
            agent_email=agent_data['email'],
            agent_phone=agent_data.get('phone', ''),
            qr_key=qr_key,
            agent_photo_key=agent_photo_key,
            sign_color=order['sign_color'],
            sign_size=normalized_size,
            order_id=order_id,
            qr_value=qr_value,
        )
        
        if not new_pdf_key:
             return jsonify({"success": False, "error": "render_failed"}), 500

        # Generate new preview
        preview_key = render_pdf_to_web_preview(
            pdf_key=new_pdf_key,
            order_id=order_id,
            sign_size=normalized_size,
        )
        
        if not preview_key:
             return jsonify({"success": False, "error": "render_failed"}), 500
        
        # Update database with new key
        db.execute(
            "UPDATE orders SET sign_size = %s, sign_pdf_path = %s WHERE id = %s",
            (normalized_size, new_pdf_key, order_id)
        )
        db.commit()
        
        # Cleanup old PDF if different
        if old_pdf_key and old_pdf_key != new_pdf_key:
            try:
                storage.delete(old_pdf_key)
            except Exception as e:
                current_app.logger.warning(f"[Resize] Failed to delete old PDF: {e}")
        
        # Build URL with cache-busting timestamp
        import time
        timestamp = int(time.time())
        preview_url = url_for('orders.order_preview', order_id=order_id)
        if guest_token:
            preview_url += f'?guest_token={guest_token}&v={timestamp}'
        else:
            preview_url += f'?v={timestamp}'
            
        return jsonify({
            "success": True,
            "size": normalized_size,
            "pdf_url": url_for('orders.download_pdf', order_id=order_id),
            "preview_url": preview_url,
        })
        
    except Exception as e:
        current_app.logger.error(f"[Orders] Resize failed for order {order_id}: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": "render_failed", "message": str(e)}), 500
