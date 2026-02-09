from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, jsonify, abort, send_file
from flask_login import login_required, current_user
import stripe
import logging
import os
import time
from models import Order, Property, db
from config import STRIPE_SIGN_SUCCESS_URL, STRIPE_SIGN_CANCEL_URL, PRIVATE_PDF_DIR, PRIVATE_PREVIEW_DIR
from utils.sign_options import normalize_sign_size, validate_sign_color

# Order Blueprint
orders_bp = Blueprint('orders', __name__)
logger = logging.getLogger(__name__)

@orders_bp.route('/orders/<int:order_id>/preview.webp')
def order_preview(order_id):
    """
    Serve the WebP preview for a specific order.
    Uses stored preview_key if available, otherwise falls back to deterministic logic (legacy).
    """
    from services.order_access import get_order_for_request
    from utils.storage import get_storage
    from utils.filenames import make_sign_asset_basename
    from constants import LAYOUT_VERSION, DEFAULT_SIGN_SIZE

    # Centralized Auth Check (Guest Friendly)
    order = get_order_for_request(order_id)
    
    storage = get_storage()
    
    # 1. Try stored key (Stable)
    if hasattr(order, 'preview_key') and order.preview_key:
        try:
            file_data = storage.get_file(order.preview_key)
            return send_file(file_data, mimetype='image/webp')
        except Exception:
            pass # Fallback to deterministic
            
    # 2. Deterministic Fallback (Legacy)
    normalized_size = normalize_sign_size(order.sign_size or DEFAULT_SIGN_SIZE)
    basename = make_sign_asset_basename(order_id, normalized_size, LAYOUT_VERSION)
    preview_key = f"previews/order_{order_id}/{basename}.webp"
    
    try:
        file_data = storage.get_file(preview_key)
        return send_file(file_data, mimetype='image/webp')
    except Exception as e:
        logger.warning(f"Preview not found for order {order_id}: {preview_key} - {e}")
        abort(404)

@orders_bp.route('/orders/yard/select')
@login_required
def select_property_for_sign():
    """
    Select a property to order a Yard Sign for.
    Redirects to Property Creation if no properties exist.
    """
    from database import get_db
    db = get_db()
    
    properties = db.execute("""
        SELECT p.* 
        FROM properties p
        JOIN agents a ON p.agent_id = a.id
        WHERE a.user_id = %s
        ORDER BY p.created_at DESC
    """, (current_user.id,)).fetchall()
    
    if not properties:
        flash("You need to add a property first.", "warning")
        return redirect(url_for('agent.submit'))
    
    # Attach gating status for UI (expired/unpaid labels)
    from services.gating import get_property_gating_status
    enriched_properties = []
    
    # Convert Row objects to dicts to allow modification
    # Or just wrap them. Since Row objects might be read-only or rigid, it's safer to create a wrapper list.
    for prop in properties:
        p_dict = dict(prop)
        gating = get_property_gating_status(p_dict['id'])
        p_dict['gating'] = gating
        enriched_properties.append(p_dict)
        
    from datetime import datetime
    return render_template('orders/select_property.html', properties=enriched_properties, now=datetime.now())

@orders_bp.route('/orders/<int:order_id>/download')
def download_pdf(order_id):
    abort(404)

@orders_bp.route('/order/sign/start/<int:property_id>')
@login_required
def order_sign_start(property_id):
    prop = Property.get(property_id)
    if not prop:
        abort(404)
    if prop.agent.user_id != current_user.id:
        abort(403)
    return render_template('order_sign.html', property=prop)

@orders_bp.route('/order-sign', methods=['POST'])
def order_sign():
    """
    Create a Stripe Checkout Session for a Yard Sign.
    Guest Supported.
    """
    from services.order_access import get_order_for_request
    data = request.get_json()
    order_id = data.get('order_id')
    
    # 1. Resolve Order & Auth
    if order_id:
        # Use centralized helper (Supports Guest)
        order = get_order_for_request(order_id)
    else:
        # New Order Logic - MUST require Login for now to create NEW from property
        # (Unless we add property guest access logic, but goal is flow repair for EXISTING flow)
        if not current_user.is_authenticated:
             return jsonify({"success": False, "error": "Login required to start new order"}), 401
             
        property_id = data.get('property_id')
        if not property_id:
            return jsonify({"success": False, "error": "Property ID required"}), 400
            
        prop = Property.get(property_id)
        if not prop or (prop.agent.user_id != current_user.id and not current_user.is_admin):
             return jsonify({"success": False, "error": "Unauthorized"}), 403
             
        from database import get_db
        db_conn = get_db()
        import secrets
        guest_token = secrets.token_urlsafe(32)
        
        # Canonical: order_type='sign', print_product set later
        row = db_conn.execute("""
            INSERT INTO orders (
                user_id, property_id, status, 
                order_type, guest_token, guest_token_created_at, created_at
            ) VALUES (%s, %s, %s, %s, %s, NOW(), NOW())
            RETURNING id
        """, (current_user.id, property_id, 'pending_payment', 'sign', guest_token)).fetchone()
        
        db_conn.commit()
        order = Order.get(row['id'])

    # 2. Apply Options (Guest Safe)
    from database import get_db
    db_conn = get_db()
    
    req_size = data.get('size') or data.get('sign_size')
    req_color = data.get('color') or data.get('sign_color')
    
    if req_size or req_color:
        updates = ["status = 'pending_payment'", "updated_at = NOW()"]
        params = []
        if req_size:
            updates.append("sign_size = %s")
            params.append(normalize_sign_size(req_size))
        if req_color:
            updates.append("sign_color = %s")
            params.append(validate_sign_color(req_color))
            
        params.append(order.id)
        db_conn.execute(f"UPDATE orders SET {', '.join(updates)} WHERE id = %s", tuple(params))
        db_conn.commit()
        # Reload
        order = Order.get(order.id)

    # 3. Checkout Setup
    # Guest Email Handling
    customer_email = None
    if current_user.is_authenticated:
        customer_email = current_user.email
    elif data.get('email'):
        customer_email = data.get('email')
        
        # Persist guest email if new/changed
        # Note: We only set this for unauthenticated orders
        if order.guest_email != customer_email:
             db_conn.execute("UPDATE orders SET guest_email = %s WHERE id = %s", (customer_email, order.id))
             db_conn.commit()
        
    raw_sign_size = order.sign_size
    sign_size = normalize_sign_size(raw_sign_size)
    material = data.get('material', 'coroplast_4mm')
    sides = 'double'
    
    from services.print_catalog import get_price_id
    try:
        price_id = get_price_id('yard_sign', sign_size, material)
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
        
    db_conn.execute("""
        UPDATE orders 
        SET print_product = %s, material = %s, sides = %s, print_size = %s, layout_id = %s, updated_at = NOW()
        WHERE id = %s
    """, ('yard_sign', material, sides, sign_size, data.get('layout_id', order.layout_id or 'yard_standard'), order.id))
    db_conn.commit()
    
    try:
        curr_user_id = str(current_user.id) if current_user.is_authenticated else "guest"
        
        checkout_params = {
            'line_items': [{'price': price_id, 'quantity': 1}],
            'mode': 'payment',
            'success_url': STRIPE_SIGN_SUCCESS_URL,
            'cancel_url': STRIPE_SIGN_CANCEL_URL,
            'client_reference_id': str(order.id),
            'shipping_address_collection': {'allowed_countries': ['US']},
            'metadata': {
                'order_id': str(order.id),
                'property_id': str(order.property_id),
                'user_id': curr_user_id,
                'sign_type': 'yard_sign', # Keep for analytics/reference? Or change to 'sign'? Leaving as descriptive 'yard_sign' is fine for metadata.
                'material': material,
                'sides': sides,
                'size': sign_size
            }
        }
        
        if customer_email:
            checkout_params['customer_email'] = customer_email
            
        checkout_session = stripe.checkout.Session.create(**checkout_params)
        return jsonify({"success": True, "checkoutUrl": checkout_session.url})
        
    except Exception as e:
        logger.error(f"Stripe setup failed: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": f"Stripe Setup Error: {str(e)}", "details": str(e)}), 500

@orders_bp.route('/order/success')
def order_success():
    """
    Order Success Page - READ-ONLY.
    
    This page is purely informational. All fulfillment and state mutation
    is handled exclusively by webhooks via services.orders.process_paid_order.
    """
    session_id = request.args.get('session_id')
    return render_template('order_success.html', session_id=session_id)

@orders_bp.route('/order/cancel')
def order_cancel():
    return render_template('order_cancel.html')

@orders_bp.route('/api/orders/resize', methods=['POST'])
def resize_order():
    """
    Resize an existing order.
    Guest Supported.
    """
    from database import get_db
    from services.printing.yard_sign import generate_yard_sign_pdf_from_order_row
    from utils.pdf_preview import render_pdf_to_web_preview
    from constants import SIGN_SIZES
    from services.order_access import get_order_for_request
    
    data = request.get_json()
    order_id = data.get('order_id')
    new_size = data.get('size')
    
    if not order_id or not new_size:
        return jsonify({'success': False, 'error': 'missing_params'}), 400
        
    normalized_size = normalize_sign_size(new_size)
    if normalized_size not in SIGN_SIZES:
        return jsonify({'success': False, 'error': 'invalid_size'}), 400
        
    # Centralized Auth (Guest Friendly)
    try:
        order = get_order_for_request(order_id)
    except Exception:
        return jsonify({'success': False, 'error': 'unauthorized'}), 403
        
    if order.status not in ('pending_payment', None):
        return jsonify({'success': False, 'error': 'order_locked_paid'}), 400
        
    db = get_db()
    try:
        # Update size in order first, then reload as dict row
        db.execute("""
            UPDATE orders 
            SET sign_size = %s,
                print_size = %s,
                updated_at = NOW()
            WHERE id = %s
        """, (normalized_size, normalized_size, order_id))
        db.commit()
        
        # Load full order row as dict for the unified generator
        order_row = db.execute("SELECT * FROM orders WHERE id = %s", (order_id,)).fetchone()
        if not order_row:
            return jsonify({'success': False, 'error': 'order_not_found'}), 404
        
        # Convert to dict if needed
        if hasattr(order_row, '_asdict'):
            order_row = order_row._asdict()
        elif not isinstance(order_row, dict):
            order_row = dict(order_row)
        
        # For yard signs, we generate immediately (if we have data)
        # But usually we wait for webhook. However, if we want preview?
        # Preview logic is separate. This route is for re-generation? 
        # Actually this route seems to be "fulfill_pdf"?
        pdf_key = generate_yard_sign_pdf_from_order_row(order_row, db=db)
        
        # Regenerate preview (Returns Key)
        preview_key = render_pdf_to_web_preview(
            pdf_key=pdf_key,
            order_id=order_id,
            sign_size=normalized_size,
        )
        
        # Update DB with new keys
        try:
             db.execute("""
                UPDATE orders 
                SET sign_pdf_path = %s,
                    preview_key = %s,
                    updated_at = NOW()
                WHERE id = %s
            """, (pdf_key, preview_key, order_id))
        except Exception as e:
            # Fallback for schema lag
             db.execute("""
                UPDATE orders 
                SET sign_pdf_path = %s,
                    updated_at = NOW()
                WHERE id = %s
            """, (pdf_key, order_id))
            
        db.commit()
        
        # Build preview URL with guest token if needed
        preview_args = {'order_id': order_id}
        if request.json.get('guest_token'):
            preview_args['guest_token'] = request.json.get('guest_token')
            
        preview_url = url_for('orders.order_preview', **preview_args)
        
        return jsonify({
            'success': True,
            'size': normalized_size,
            'preview_url': preview_url
        })
        
    except Exception as e:
        logger.error(f"Resize failed: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': 'render_failed', 'message': str(e)}), 500



@orders_bp.route('/orders/smart-sign/checkout', methods=['POST'])
@login_required
def smart_sign_checkout():
    # Deprecated endpoint (legacy Option B). Canonical SmartSign ordering lives under /smart-signs.
    # Intentionally disabled to prevent drift and accidental use.
    abort(404)

@orders_bp.route('/orders/listing/select')
@login_required
def select_property_legacy_redirect():
    """Backward compatibility for old 'listing sign' ordering URL."""
    return redirect(url_for('orders.select_property_for_sign'))
