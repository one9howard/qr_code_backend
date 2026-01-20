from flask import Blueprint, request, jsonify, render_template, redirect, url_for, flash, send_file, current_app, abort
from flask_login import login_required, current_user
import stripe
import os

from database import get_db
from config import STRIPE_SECRET_KEY, STRIPE_SIGN_SUCCESS_URL, STRIPE_SIGN_CANCEL_URL
from services.pdf_smartsign import generate_smartsign_pdf
from utils.storage import get_storage
from services.stripe_checkout import create_checkout_attempt, update_attempt_status

smart_signs_bp = Blueprint('smart_signs', __name__)

# Constants
PRESET_BACKGROUNDS = ['solid_blue', 'dark', 'light']
PRESET_CTAS = [
    'scan_for_details', 'scan_to_view', 'scan_for_photos', 
    'scan_to_schedule', 'scan_to_connect', 'scan_for_info'
]

def get_smartsign_price():
    """Deterministic pricing for SmartSigns."""
    # Priority 1: Specific Env Var
    price_cents = os.environ.get('SMARTSIGN_PRICE_CENTS')
    if price_cents:
        return int(price_cents), 'cents'
        
    # Priority 2: Specific Stripe Price ID
    price_id = os.environ.get('STRIPE_PRICE_SMARTSIGN')
    if price_id:
        return price_id, 'id'
        
    # STRICT FAILURE
    return None, None

def check_access(asset_id):
    """
    Verify ownership, pro status, and frozen status.
    Returns asset or aborts.
    """
    db = get_db()
    asset = db.execute("SELECT * FROM sign_assets WHERE id = %s", (asset_id,)).fetchone()
    
    if not asset:
        abort(404)
        
    if asset['user_id'] != current_user.id:
        abort(403)
        
    # Pro check (canonical)
    from services.subscriptions import is_subscription_active
    if not is_subscription_active(current_user.subscription_status):
        flash("SmartSigns are a Pro feature.", "warning")
        abort(403) # Or redirect to upgrade
        
    return asset

@smart_signs_bp.route("/dashboard/sign-assets/<int:asset_id>/edit", methods=["GET", "POST"])
@login_required
def edit_smartsign(asset_id):
    asset = check_access(asset_id)
    
    # Frozen check for edit
    if asset['is_frozen']:
        flash("Frozen assets cannot be edited.", "error")
        return redirect(url_for('dashboard.index'))

    if request.method == "POST":
        # Form handling
        brand_name = request.form.get('brand_name')
        phone = request.form.get('phone')
        email = request.form.get('email')
        
        cta_key = request.form.get('cta_key')
        if cta_key not in PRESET_CTAS: cta_key = 'scan_for_details'
        
        bg_style = request.form.get('background_style')
        if bg_style not in PRESET_BACKGROUNDS: bg_style = 'solid_blue'
        
        include_logo = request.form.get('include_logo') == 'on'
        include_headshot = request.form.get('include_headshot') == 'on'
        
        # Image Uploads
        storage = get_storage()
        logo_file = request.files.get('logo_file')
        headshot_file = request.files.get('headshot_file')
        
        logo_key = asset['logo_key']
        if logo_file and logo_file.filename:
            # Simple unique naming
            ext = os.path.splitext(logo_file.filename)[1]
            key = f"uploads/brands/{current_user.id}_{asset['id']}_logo{ext}"
            logo_key = storage.put_file(logo_file, key)
            
        headshot_key = asset['headshot_key']
        if headshot_file and headshot_file.filename:
            ext = os.path.splitext(headshot_file.filename)[1]
            key = f"uploads/brands/{current_user.id}_{asset['id']}_head{ext}"
            headshot_key = storage.put_file(headshot_file, key)

        db = get_db()
        db.execute("""
            UPDATE sign_assets 
            SET brand_name=%s, phone=%s, email=%s, cta_key=%s, background_style=%s,
                include_logo=%s, include_headshot=%s, logo_key=%s, headshot_key=%s,
                updated_at=CURRENT_TIMESTAMP
            WHERE id=%s
        """, (brand_name, phone, email, cta_key, bg_style, 
              include_logo, include_headshot, logo_key, headshot_key, 
              asset_id))
        db.commit()
        
        flash("Design updated.", "success")
        return redirect(url_for('smart_signs.edit_smartsign', asset_id=asset_id))

    return render_template('smartsign_edit.html', asset=asset, 
                           bg_options=PRESET_BACKGROUNDS, cta_options=PRESET_CTAS)

@smart_signs_bp.route("/dashboard/sign-assets/<int:asset_id>/preview")
@login_required
def preview_smartsign(asset_id):
    asset = check_access(asset_id)
    # Allow preview even if frozen? Yes, user might want to see what they have.
    
    # Generate on the fly (or cache logic could be added)
    # We call generator which returns storage KEY
    pdf_key = generate_smartsign_pdf(asset, order_id=None) # No order ID for preview
    
    storage = get_storage()
    if not storage.exists(pdf_key):
        abort(404, "PDF generation failed")
        
    try:
        file_bytes = storage.get_file(pdf_key)
        return send_file(
            file_bytes,
            mimetype="application/pdf",
            as_attachment=False, # Inline for preview
            download_name="preview.pdf"
        )
    except Exception as e:
        current_app.logger.error(f"Preview error: {e}")
        abort(500)

@smart_signs_bp.route("/orders/smart-sign/start")
@login_required
def order_start():
    price_val, price_type = get_smartsign_price()
    if not price_val:
        flash("Ordering currently unavailable (Configuration Error).", "error")
        return redirect(url_for('dashboard.index'))

    asset_id = request.args.get('asset_id')
    asset = None
    properties = []
    
    if asset_id:
        # Reorder / Existing
        asset = check_access(asset_id)
        if asset['is_frozen']:
            flash("Frozen assets cannot be ordered. Unlock first.", "error")
            return redirect(url_for('dashboard.index'))
    else:
        # New Order -> Create New Asset
        # Verify user is Pro (Canonical)
        from services.subscriptions import is_subscription_active
        if not is_subscription_active(current_user.subscription_status):
             flash("Upgrade required to order SmartSigns.", "warning")
             return redirect(url_for('billing.index'))
             
        # Fetch properties for dropdown
        db = get_db()
        properties = db.execute("""
            SELECT p.id, p.address 
            FROM properties p
            JOIN agents a ON p.agent_id = a.id
            WHERE a.user_id = %s
            ORDER BY p.created_at DESC
        """, (current_user.id,)).fetchall()
        
    return render_template('smartsign_order_start.html', 
                           asset=asset, 
                           properties=properties,
                           price=price_val, 
                           price_type=price_type)

@smart_signs_bp.route("/orders/smart-sign/checkout", methods=["POST"])
@login_required
def checkout_smartsign():
    asset_id = request.form.get('asset_id')
    property_id = request.form.get("property_id")
    
    asset = None
    
    # 0. Pricing Check
    price_val, price_type = get_smartsign_price()
    if not price_val:
        flash("Ordering configuration error.", "error")
        return redirect(url_for('dashboard.index'))

    if asset_id:
        # Reorder Existing
        asset = check_access(asset_id)
        if asset['is_frozen']:
            flash("Frozen assets cannot be ordered.", "error")
            return redirect(url_for('dashboard.index'))
    else:
        # New Asset Creation
        if not property_id:
             flash("Please select a property to assign the sign to.", "error")
             return redirect(url_for('smart_signs.order_start'))
             
        try:
             # Validate property ownership implicitly via create_asset logic if we moved it there? 
             # No, create_asset doesn't checking prop ownership deeply yet?
             # Actually `create_asset` takes `active_property_id`. We rely on it (or should verify first).
             # Let's verify property quickly to be safe (or trust service layer if updated).
             # Service layer update didn't include property ownership check for creation, only assignment.
             # So we should check it here or update service. Using ad-hoc check for speed/safety.
             db = get_db()
             valid_prop = db.execute("""
                SELECT 1 FROM properties p JOIN agents a ON p.agent_id = a.id 
                WHERE p.id = %s AND a.user_id = %s
             """, (property_id, current_user.id)).fetchone()
             if not valid_prop:
                 raise ValueError("Invalid property selected.")

             from services.smart_signs import SmartSignsService
             asset_row = SmartSignsService.create_asset_for_purchase(
                 current_user.id, 
                 property_id=property_id, 
                 label=None
             )
             # asset_row is a Row object, need dict-like access or just ID
             asset = dict(asset_row)
             asset_id = asset['id']
             
        except Exception as e:
             flash(f"Error initiating sign: {e}", "error")
             return redirect(url_for('smart_signs.order_start'))

    db = get_db()
    stripe.api_key = STRIPE_SECRET_KEY

    # 1. Create Order
    # We use a distinct order_type "smart_sign"
    # OPTION B: SmartSign orders MUST have a property_id (NOT NULL)
    row = db.execute("""
        INSERT INTO orders (user_id, property_id, sign_asset_id, status, order_type, created_at)
        VALUES (%s, %s, %s, 'pending_payment', 'smart_sign', CURRENT_TIMESTAMP)
        RETURNING id
    """, (current_user.id, property_id, asset_id)).fetchone()
    order_id = row['id']
    db.commit() # Commit to get ID
    
    # 2. Build Stripe Params
    line_item = {
        'quantity': 1,
    }
    
    code_display = asset['code'] if asset else "NEW"
    
    if price_type == 'id':
        line_item['price'] = price_val
    else:
        # Cents
        line_item['price_data'] = {
            'currency': 'usd',
            'product_data': {
                'name': f"SmartSign Print: {code_display}",
                'description': "18x24 PVC SmartSign (Pro)",
            },
            'unit_amount': price_val,
        }

    checkout_params = {
        'line_items': [line_item],
        'mode': 'payment',
        'success_url': STRIPE_SIGN_SUCCESS_URL,
        'cancel_url': STRIPE_SIGN_CANCEL_URL,
        'customer_email': current_user.email,
        'client_reference_id': str(order_id),
        'metadata': {
            'order_id': str(order_id),
            'purpose': 'smart_sign',
            'sign_asset_id': str(asset_id),
            'property_id': str(property_id),
            'user_id': str(current_user.id)
        }
    }

    # 3. Create Session (using checkout service helper for consistency)
    try:
        attempt = create_checkout_attempt(
            user_id=current_user.id,
            purpose='smart_sign',
            params=checkout_params,
            order_id=order_id
        )
        
        checkout_params['metadata']['attempt_token'] = attempt['attempt_token']
        
        session = stripe.checkout.Session.create(
            **checkout_params,
            idempotency_key=attempt['idempotency_key']
        )
        
        update_attempt_status(
            attempt['attempt_token'],
            'session_created',
            stripe_session_id=session.id
        )
        
        db.execute("UPDATE orders SET stripe_checkout_session_id=%s WHERE id=%s", (session.id, order_id))
        db.commit()
        
        # Determine strictness of redirect
        return redirect(session.url, code=303)
        
    except Exception as e:
        current_app.logger.error(f"SmartSign checkout error: {e}")
        flash("Checkout initialization failed. Please try again.", "error")
        # Go back to start, preserving asset_id if it was a reorder
        return redirect(url_for('smart_signs.order_start', asset_id=request.form.get('asset_id')))
