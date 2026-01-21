from flask import Blueprint, request, render_template, jsonify, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
import stripe
import os
import json
from config import STRIPE_SECRET_KEY, STRIPE_SIGN_SUCCESS_URL, STRIPE_SIGN_CANCEL_URL
from models import db, Order, User
from services.gating import gating_service, get_smart_sign_assets
from utils.storage import get_storage
from services.events import track_event

smart_signs_bp = Blueprint('smart_signs', __name__, url_prefix='/smart-signs')

@smart_signs_bp.route('/manage')
@login_required
def manage():
    """Dashboard for managing SmartSigns."""
    assets = get_smart_sign_assets(current_user.id)
    return render_template('smart_signs/manage.html', assets=assets)

@smart_signs_bp.route('/assign', methods=['POST'])
@login_required
def assign_property():
    """Assign a property to a SmartSign asset."""
    asset_id = request.form.get('asset_id')
    property_id = request.form.get('property_id')
    
    if not asset_id or not property_id:
        flash("Missing asset or property selection.", "error")
        return redirect(url_for('smart_signs.manage'))
        
    success, message = gating_service.assign_smart_sign(current_user.id, asset_id, property_id)
    if success:
        flash("SmartSign assigned successfully.", "success")
    else:
        flash(message, "error")
        
    return redirect(url_for('smart_signs.manage'))

@smart_signs_bp.route('/unassign', methods=['POST'])
@login_required
def unassign_property():
    """Unassign a property from a SmartSign."""
    asset_id = request.form.get('asset_id')
    if not asset_id:
        flash("Missing asset ID.", "error")
        return redirect(url_for('smart_signs.manage'))
        
    success, message = gating_service.unassign_smart_sign(current_user.id, asset_id)
    if success:
        flash("SmartSign unassigned.", "success")
    else:
        flash(message, "error")
        
    return redirect(url_for('smart_signs.manage'))


# --- Purchase Flow ---

@smart_signs_bp.route('/order/start')
@login_required
def order_start():
    """
    Start the SmartSign order flow.
    Optional: asset_id to re-order/replace typical hardcopy? 
    Usually this is for a new physical sign.
    """
    asset_id = request.args.get('asset_id')
    colors = [
        {'id': 'blue', 'name': 'Blue', 'hex': '#0077ff'},
        {'id': 'navy', 'name': 'Navy', 'hex': '#0f172a'},
        {'id': 'black', 'name': 'Black', 'hex': '#000000'},
        {'id': 'white', 'name': 'White', 'hex': '#ffffff'},
        {'id': 'red', 'name': 'Red', 'hex': '#ef4444'},
        {'id': 'green', 'name': 'Green', 'hex': '#22c55e'},
        {'id': 'orange', 'name': 'Orange', 'hex': '#f97316'},
        {'id': 'gray', 'name': 'Gray', 'hex': '#64748b'},
    ]
    
    prefill = {}
    if asset_id:
        # If ordering for existing asset (replacement?), prefill
        pass
        
    return render_template('smart_signs/order_form.html', colors=colors, asset_id=asset_id)


def check_access(asset_id):
    # Helper to check ownership
    data = db.session.execute("SELECT * FROM smart_sign_assets WHERE id=:id AND user_id=:uid", {"id": asset_id, "uid": current_user.id}).fetchone()
    if not data:
        abort(404)
    return dict(data)

@smart_signs_bp.route('/checkout', methods=['POST'])
@login_required
def checkout_smartsign():
    """
    Handle SmartSign Checkout.
    Strict Phase 6 Logic:
    - Aluminum Only
    - Double Sided Only
    - Strict Size/Layout validation
    - Lookup Key Pricing
    """
    # Use request.form mostly since we handle file uploads here too?
    # Or JS sends JSON + separate file upload?
    # Assuming Form POST with files for this implementation based on previous code.
    
    # However, standard pattern is often JS FormData.
    
    asset_id = request.form.get('asset_id') # Optional
    
    # 1. Extract and Validate Basic Info
    size = request.form.get('size')
    layout_id = request.form.get('layout_id')
    
    if not size or not layout_id:
        flash("Size and Layout are required.", "error")
        return redirect(url_for('smart_signs.order_start'))

    # Strict Product Rules
    print_product = 'smart_sign'
    material = 'aluminum_040' # Force
    sides = 'double'          # Force
    
    # 2. Files & Storage
    storage = get_storage()
    
    # Retrieve existing keys if asset_id provided (cloning/reordering)
    # For now assume new or provided in form
    headshot_key = request.form.get('agent_headshot_key') # Hidden input?
    logo_key = request.form.get('agent_logo_key')
    
    if request.files.get('headshot_file'):
        f = request.files['headshot_file']
        if f.filename:
            ext = os.path.splitext(f.filename)[1]
            k = f"uploads/brands/{current_user.id}_new_head{ext}"
            headshot_key = storage.put_file(f, k)
            
    if request.files.get('logo_file'):
        f = request.files['logo_file']
        if f.filename:
            ext = os.path.splitext(f.filename)[1]
            k = f"uploads/brands/{current_user.id}_new_logo{ext}"
            logo_key = storage.put_file(f, k)

    # 3. Design Payload
    payload = {
        'banner_color_id': request.form.get('banner_color_id'),
        'agent_name': request.form.get('agent_name'),
        'agent_phone': request.form.get('agent_phone'),
        'agent_email': request.form.get('agent_email'),
        'brokerage_name': request.form.get('brokerage_name'),
        'agent_headshot_key': headshot_key,
        'agent_logo_key': logo_key
    }
    
    # 4. Validation (Strict)
    from services.printing.validation import validate_smartsign_payload
    errors = validate_smartsign_payload(layout_id, payload)
    if errors:
        for e in errors: flash(e, 'error')
        return redirect(url_for('smart_signs.order_start', asset_id=asset_id))

    # 5. Pricing (Catalog)
    from services.print_catalog import get_price_id
    try:
        price_id = get_price_id(print_product, size, material)
    except ValueError as e:
        flash(f"Configuration Error: {e}", "error")
        return redirect(url_for('smart_signs.order_start'))

    # 6. Asset Creation (If new)
    property_id = None
    if asset_id:
        # Check frozen
        pass 
    else:
        # Create new Pending Asset
        # (Logic omitted for brevity, assuming standard flow creates asset later or here)
        pass

    # 7. Create Order
    order = Order(
        user_id=current_user.id,
        order_type='smart_sign',
        status='pending',
        print_product=print_product,
        material=material,
        sides=sides,
        print_size=size,
        layout_id=layout_id,
        design_payload=payload,  # JSONB
        design_version=1
    )
    db.session.add(order)
    db.session.commit()
    
    # 8. Stripe Session
    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price': price_id,
                'quantity': 1,
            }],
            mode='payment',
            success_url=STRIPE_SIGN_SUCCESS_URL,
            cancel_url=STRIPE_SIGN_CANCEL_URL,
            client_reference_id=str(order.id),
            metadata={
                'order_id': order.id,
                'user_id': current_user.id,
                'type': 'smart_sign',
                'size': size
            }
        )
        
        # If AJAX, return JSON. If Form, redirect.
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'checkoutUrl': checkout_session.url})
        return redirect(checkout_session.url, code=303)
        
    except Exception as e:
        current_app.logger.error(f"Stripe Error: {e}")
        flash("Payment initialization failed.", "error")
        return redirect(url_for('smart_signs.order_start'))
