from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, jsonify, abort, send_file
from flask_login import login_required, current_user
import stripe
import logging
import os
import time
from models import Order, Property, db
from config import STRIPE_SIGN_SUCCESS_URL, STRIPE_SIGN_CANCEL_URL, PRIVATE_PDF_DIR, PRIVATE_PREVIEW_DIR
from utils.sign_options import normalize_sign_size

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

@orders_bp.route('/orders/listing/select')
@login_required
def select_property_for_sign():
    """
    Select a property to order a listing sign for.
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
    Create a Stripe Checkout Session for a Listing Sign.
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
            params.append(req_color)
            
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
        price_id = get_price_id('listing_sign', sign_size, material)
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
        
    db_conn.execute("""
        UPDATE orders 
        SET print_product = %s, material = %s, sides = %s, print_size = %s, layout_id = %s, updated_at = NOW()
        WHERE id = %s
    """, ('listing_sign', material, sides, sign_size, data.get('layout_id', order.layout_id or 'standard'), order.id))
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
                'sign_type': 'listing_sign', # Keep for analytics/reference? Or change to 'sign'? Leaving as descriptive 'listing_sign' is fine for metadata.
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
        return jsonify({"success": False, "error": str(e)}), 500

@orders_bp.route('/order/success')
def order_success():
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
    from database import get_db, get_agent_data_for_order
    from utils.pdf_generator import generate_pdf_sign
    from utils.pdf_preview import render_pdf_to_web_preview
    from utils.qr_urls import property_scan_url
    from constants import SIGN_SIZES, DEFAULT_SIGN_COLOR
    from config import BASE_URL
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
        prop = db.execute("SELECT * FROM properties WHERE id = %s", (order.property_id,)).fetchone()
        if not prop: return jsonify({'success': False, 'error': 'property_not_found'}), 404
        
        agent = get_agent_data_for_order(order_id)
        if not agent: return jsonify({'success': False, 'error': 'agent_not_found'}), 404
        
        qr_code = prop.get('qr_code')
        if not qr_code: return jsonify({'success': False, 'error': 'missing_qr_code'}), 500
        qr_url = property_scan_url(BASE_URL, qr_code)
        
        sign_color = order.sign_color or DEFAULT_SIGN_COLOR
        
        # NOTE: If we persisted logo/headshot choice in order/agent snapshot, we'd pull it here.
        # Currently assuming snapshot has correct keys.
        
        pdf_key = generate_pdf_sign(
            address=prop.get('address', ''),
            beds=prop.get('beds', ''),
            baths=prop.get('baths', ''),
            sqft=prop.get('sqft', ''),
            price=prop.get('price', ''),
            agent_name=agent.get('name', ''),
            brokerage=agent.get('brokerage', ''),
            agent_email=agent.get('email', ''),
            agent_phone=agent.get('phone', ''),
            qr_key=None,
            agent_photo_key=agent.get('photo_filename'),
            sign_color=sign_color,
            sign_size=normalized_size,
            order_id=order_id,
            qr_value=qr_url,
            # Pass logo only if column exists in snapshot or we fetch from agent (Snapshot update needed for full fidelity)
            logo_key=agent.get('logo_filename') if 'logo_filename' in agent else None,
            user_id=order.user_id # NEW: Pass owner ID for QR logo rendering
        )
        
        # Regenerate preview (Returns Key)
        preview_key = render_pdf_to_web_preview(
            pdf_key=pdf_key,
            order_id=order_id,
            sign_size=normalized_size,
        )
        
        # Update DB (including preview_key)
        # Check if preview_key column exists before writing (safety)
        # Using Safe Update
        try:
             db.execute("""
                UPDATE orders 
                SET sign_size = %s,
                    print_size = %s,
                    sign_pdf_path = %s,
                    preview_key = %s,
                    updated_at = NOW()
                WHERE id = %s
            """, (normalized_size, normalized_size, pdf_key, preview_key, order_id))
        except Exception as e:
            # Fallback for schema lag
             db.execute("""
                UPDATE orders 
                SET sign_size = %s,
                    print_size = %s,
                    sign_pdf_path = %s,
                    updated_at = NOW()
                WHERE id = %s
            """, (normalized_size, normalized_size, pdf_key, order_id))
            
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
    """
    SmartSign Option B Checkout Endpoint.
    
    Required Form Data:
    - asset_id: The sign_asset to purchase
    - property_id: The property to associate with the order
    
    Creates an order and redirects to Stripe Checkout.
    """
    from database import get_db
    
    db = get_db()
    
    # 1. Read form data
    asset_id = request.form.get('asset_id')
    property_id = request.form.get('property_id')
    
    if not asset_id or not property_id:
        return jsonify({'error': 'asset_id and property_id are required'}), 400
    
    try:
        asset_id = int(asset_id)
        property_id = int(property_id)
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid asset_id or property_id'}), 400
    
    # 2. Validate asset ownership
    asset = db.execute(
        "SELECT * FROM sign_assets WHERE id = %s AND user_id = %s",
        (asset_id, current_user.id)
    ).fetchone()
    
    if not asset:
        return jsonify({'error': 'Asset not found or not owned by user'}), 404
    
    # 3. Create order
    order_row = db.execute("""
        INSERT INTO orders (
            user_id, property_id, sign_asset_id, order_type, status, created_at
        ) VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
        RETURNING id
    """, (
        current_user.id,
        property_id,
        asset_id,
        'smart_sign',
        'pending_payment'
    )).fetchone()
    order_id = order_row['id']
    db.commit()
    
    # 4. Create Stripe Checkout Session
    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'unit_amount': int(os.environ.get('SMARTSIGN_PRICE_CENTS', 5000)),
                    'product_data': {
                        'name': 'SmartSign',
                    },
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=STRIPE_SIGN_SUCCESS_URL,
            cancel_url=STRIPE_SIGN_CANCEL_URL,
            client_reference_id=str(order_id),
            metadata={
                'purpose': 'smart_sign',
                'property_id': str(property_id),
                'order_id': str(order_id),
                'sign_asset_id': str(asset_id),
                'user_id': str(current_user.id)
            }
        )
        
        # 5. Save stripe session ID
        db.execute(
            "UPDATE orders SET stripe_checkout_session_id = %s WHERE id = %s",
            (checkout_session.id, order_id)
        )
        db.commit()
        
        # 6. Redirect to Stripe
        return redirect(checkout_session.url, code=303)
        
    except Exception as e:
        logger.error(f"SmartSign checkout error: {e}")
        return jsonify({'error': str(e)}), 500

