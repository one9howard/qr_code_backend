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
    # Delegate to Service
    from services.orders import create_sign_order

    data = request.get_json(silent=True)
    if not data:
        data = request.form.to_dict()

    result = create_sign_order(current_user, data)
    
    status_code = 200
    if not result.get('success'):
        status_code = 400
        # If specific error codes/types were needed, we could parse result['error']
        if "Unauthorized" in result.get('error', ''):
            status_code = 403
        elif "Login required" in result.get('error', ''):
            status_code = 401
            
    return jsonify(result), status_code

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
    
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({'success': False, 'error': 'invalid_json'}), 400

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
        guest_token = data.get('guest_token')
        if guest_token:
            preview_args['guest_token'] = guest_token
            
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
