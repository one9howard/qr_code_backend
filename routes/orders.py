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
    Uses deterministic preview key from storage (no preview_path column).
    Supports both authenticated users and guest_token access.
    """
    from io import BytesIO
    from utils.storage import get_storage
    from utils.filenames import make_sign_asset_basename
    from constants import LAYOUT_VERSION, DEFAULT_SIGN_SIZE
    
    order = Order.get(order_id)
    if not order:
        abort(404)
    
    # Authorization check:
    # 1. Authenticated user who owns the order OR is admin
    # 2. Guest with valid guest_token
    authorized = False
    
    if current_user.is_authenticated:
        if current_user.id == order.user_id or getattr(current_user, 'is_admin', False):
            authorized = True
    
    if not authorized:
        # Check guest_token from query params
        guest_token = request.args.get('guest_token')
        if guest_token and order.guest_token and guest_token == order.guest_token:
            authorized = True
    
    if not authorized:
        abort(403)
    
    # Compute deterministic preview key
    normalized_size = normalize_sign_size(order.sign_size or DEFAULT_SIGN_SIZE)
    basename = make_sign_asset_basename(order_id, normalized_size, LAYOUT_VERSION)
    preview_key = f"previews/order_{order_id}/{basename}.webp"
    
    # Fetch from storage
    storage = get_storage()
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
    
    # Fetch user properties
    # Cannot rely on current_user.properties based on simple User model
    # Use raw SQL or property join.
    # We need properties linked to agents owned by this user
    
    properties = db.execute("""
        SELECT p.* 
        FROM properties p
        JOIN agents a ON p.agent_id = a.id
        WHERE a.user_id = %s AND (p.expires_at IS NULL OR p.expires_at > NOW())
        ORDER BY p.created_at DESC
    """, (current_user.id,)).fetchall()
    
    if not properties:
        flash("You need to add a property first.", "warning")
        return redirect(url_for('agent.submit'))
        
    from datetime import datetime
    return render_template('orders/select_property.html', properties=properties, now=datetime.now())

@orders_bp.route('/orders/<int:order_id>/download')
def download_pdf(order_id):
    """
    Download the generated PDF for an order.
    Disabled for MVP Phase 5/6 - Fulfillment handles printing directly.
    """
    # Disabled for MVP Phase 5/6 - Fulfillment handles printing directly.
    # Legacy code removed.
    abort(404) # Not exposed to users directly

@orders_bp.route('/order/sign/start/<int:property_id>')
@login_required
def order_sign_start(property_id):
    """
    Entry point from dashboard to order a sign.
    """
    prop = Property.get(property_id)
    if not prop:
        abort(404)
        
    # Verify ownership
    if prop.agent.user_id != current_user.id:
        abort(403)
        
    return render_template('order_sign.html', property=prop)


@orders_bp.route('/order-sign', methods=['POST'])
@login_required
def order_sign():
    """
    Create a Stripe Checkout Session for a Listing Sign.
    Strictly enforce Phase 6 rules:
    - Double-sided only
    - Valid sizes/materials only
    - Use Lookup Keys
    """
    data = request.get_json()
    order_id = data.get('order_id')
    
    # If starting fresh from order_sign_start, we might not have an order_id yet.
    # In that case, we create one now.
    
    from database import get_db
    db_conn = get_db()
    
    order = None
    if order_id:
        if current_user.is_authenticated:
            order = Order.get_by(id=order_id, user_id=current_user.id)
        else:
            # Check guest token if implemented, else fail
            # For now, require auth
            guest_token = request.headers.get("X-Guest-Token")
            if guest_token:
                 # Basic guest lookup placeholder
                 order = Order.get_by(
                    id=order_id,
                    guest_token=guest_token
                )
        if not order:
            return jsonify({"success": False, "error": "Order record not found"}), 404
            
    else:
        # Create new order on the fly
        property_id = data.get('property_id')
        if not property_id:
            return jsonify({"success": False, "error": "Property ID required if no order ID"}), 400
            
        # Verify property ownership
        prop = Property.get(property_id)
        if not prop or (prop.agent.user_id != current_user.id and not current_user.is_admin):
             return jsonify({"success": False, "error": "Unauthorized property access"}), 403
             
        # Create Order
        import secrets
        guest_token = secrets.token_urlsafe(32)
        
        # We can insert size/color here directly if we want, but the unified update block below is cleaner
        row = db_conn.execute("""
            INSERT INTO orders (
                user_id, property_id, status, 
                order_type, guest_token, guest_token_created_at, created_at
            ) VALUES (%s, %s, %s, %s, %s, NOW(), NOW())
            RETURNING id
        """, (
            current_user.id, 
            property_id, 
            'pending_payment',
            'listing_sign',
            guest_token
        )).fetchone()
        
        new_order_id = row['id']
        db_conn.commit()
        
        order = Order.get(new_order_id)

    if not order:
        return jsonify({"success": False, "error": "Failed to load order"}), 500
        
    # === Update Order with Request Options ===
    # The form sends 'size' and 'sign_color' (or 'color'). We apply them to the order.
    # This ensures the checkout price matches the selection.
    
    req_size = data.get('size') or data.get('sign_size')
    req_color = data.get('color') or data.get('sign_color')
    
    if req_size or req_color:
        updates = []
        params = []
        if req_size:
            updates.append("sign_size = %s")
            params.append(normalize_sign_size(req_size))
        if req_color:
             updates.append("sign_color = %s")
             params.append(req_color)
        
        # Force status to pending_payment on update (in case it was something else, though unlikely here)
        updates.append("status = %s")
        params.append('pending_payment')
             
        updates.append("updated_at = NOW()")

        params.append(order.id)
        
        sql = f"UPDATE orders SET {', '.join(updates)} WHERE id = %%s"
        db_conn.execute(sql, tuple(params))
        db_conn.commit()
        
        # Reload order
        order = Order.get(order.id)
        
    if not order.sign_pdf_path:
        # We allow ordering even if PDF not fully generated? 
        # Actually usually we want preview to exist.
        # But for new "productized" flow, the PDF is generated AT FULFILLMENT.
        # So we just need the metadata (design_payload) or legacy columns.
        # Legacy: checks sign_pdf_path. Phase 5/6: We might relax this if we trust the payload.
        # But currently the /submit flow generates a 'preview' and sets sign_pdf_path.
        pass

    # 3. Build checkout params
    customer_email = current_user.email if current_user.is_authenticated else None
        
    raw_sign_size = order.sign_size
    sign_size = normalize_sign_size(raw_sign_size)
    
    # Phase 6: Strict SKU & Pricing
    # 1. Read Material from request, force Sides
    material = data.get('material', 'coroplast_4mm')
    sides = 'double' # Strictly forced
    
    # 2. Validate SKU & Get Price
    from services.print_catalog import validate_sku_strict, get_price_id
    
    # get_price_id calls validate_sku_strict internally
    try:
        price_id = get_price_id('listing_sign', sign_size, material)
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
        
    # 3. Update Order with SKU Spec
    # Use direct SQL
    
    # Raw SQL Update
    # Note: We already used db_conn above, so reuse it
    db_conn.execute("""
        UPDATE orders 
        SET print_product = %s,
            material = %s,
            sides = %s,
            print_size = %s,
            layout_id = %s,
            updated_at = NOW()
        WHERE id = %s
    """, (
        'listing_sign',
        material,
        sides,
        sign_size,
        data.get('layout_id', order.layout_id or 'standard'),
        order.id
    ))
    db_conn.commit()
    
    # 4. Create Stripe Session
    try:
        # Using Price ID
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
                'sign_type': 'listing_sign',
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
    """Render success page."""
    session_id = request.args.get('session_id')
    return render_template('order_success.html', session_id=session_id)

@orders_bp.route('/order/cancel')
def order_cancel():
    """Render cancel page."""
    return render_template('order_cancel.html')


@orders_bp.route('/api/orders/resize', methods=['POST'])
@login_required
def resize_order():
    """
    Resize an existing order - regenerates BOTH PDF and preview.
    Returns JSON: {success: true, size: "...", preview_url: "..."}
    """
    from database import get_db, get_agent_data_for_order
    from utils.storage import get_storage
    from utils.pdf_generator import generate_pdf_sign
    from utils.pdf_preview import render_pdf_to_web_preview
    from utils.qr_urls import property_scan_url
    from constants import SIGN_SIZES, DEFAULT_SIGN_COLOR
    from config import BASE_URL
    
    data = request.get_json()
    order_id = data.get('order_id')
    new_size = data.get('size')
    
    if not order_id or not new_size:
        return jsonify({'success': False, 'error': 'missing_params'}), 400
    
    # Validate size
    normalized_size = normalize_sign_size(new_size)
    if normalized_size not in SIGN_SIZES:
        return jsonify({'success': False, 'error': 'invalid_size'}), 400
    
    db = get_db()
    
    # Load order - must be owned by current user
    order = Order.get_by(id=order_id, user_id=current_user.id)
    if not order:
        return jsonify({'success': False, 'error': 'unauthorized'}), 403
    
    # Check if order is already paid (locked)
    if order.status not in ('pending_payment', None):
        return jsonify({'success': False, 'error': 'order_locked_paid'}), 400
    
    try:
        # Load property
        prop = db.execute(
            "SELECT * FROM properties WHERE id = %s",
            (order.property_id,)
        ).fetchone()
        
        if not prop:
            return jsonify({'success': False, 'error': 'property_not_found'}), 404
        
        # Load agent data (snapshot preferred)
        agent = get_agent_data_for_order(order_id)
        if not agent:
            return jsonify({'success': False, 'error': 'agent_not_found'}), 404
        
        # Build QR URL from property.qr_code
        qr_code = prop.get('qr_code')
        if not qr_code:
            return jsonify({'success': False, 'error': 'missing_qr_code'}), 500
        
        qr_url = property_scan_url(BASE_URL, qr_code)
        
        # Get sign customization from order (use persisted values!)
        sign_color = order.sign_color or DEFAULT_SIGN_COLOR
        
        # Regenerate PDF with new size
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
            qr_key=None,  # Using qr_value instead
            agent_photo_key=agent.get('photo_filename'),
            sign_color=sign_color,
            sign_size=normalized_size,
            order_id=order_id,
            qr_value=qr_url,
        )
        
        # Regenerate preview
        preview_key = render_pdf_to_web_preview(
            pdf_key=pdf_key,
            order_id=order_id,
            sign_size=normalized_size,
        )
        
        # Update DB atomically
        db.execute("""
            UPDATE orders 
            SET sign_size = %s,
                print_size = %s,
                sign_pdf_path = %s,
                updated_at = NOW()
            WHERE id = %s
        """, (normalized_size, normalized_size, pdf_key, order_id))
        db.commit()
        
        # Build preview URL for response
        preview_url = url_for('orders.order_preview', order_id=order_id)
        
        return jsonify({
            'success': True,
            'size': normalized_size,
            'preview_url': preview_url
        })
        
    except Exception as e:
        logger.error(f"Resize failed for order {order_id}: {e}")
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

