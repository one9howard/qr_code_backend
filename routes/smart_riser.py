from flask import Blueprint, request, jsonify, render_template, redirect, url_for
from flask_login import login_required, current_user
from models import db, Order
from services.print_catalog import get_price_id
import stripe
import logging

smart_riser_bp = Blueprint('smart_riser', __name__, url_prefix='/smart-riser')
logger = logging.getLogger(__name__)

@smart_riser_bp.route('/checkout', methods=['POST'])
@login_required
def checkout_smart_riser():
    """
    Checkout for SmartRiser.
    Payload: { size: '6x24' | '6x36' }
    """
    data = request.get_json()
    size = data.get('size')
    
    if not size:
        return jsonify({'error': 'Missing size'}), 400
        
    # Strict Rules
    print_product = 'smart_riser'
    material = 'aluminum_040'
    sides = 'double'
    
    try:
        price_id = get_price_id(print_product, size, material)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
        
    # Create Asset (Option B)
    import uuid
    from database import get_db
    
    db = get_db()
    while True:
        code = uuid.uuid4().hex[:8].upper()
        if not db.execute("SELECT 1 FROM sign_assets WHERE code=%s", (code,)).fetchone():
            break
            
    row = db.execute("""
        INSERT INTO sign_assets (user_id, code, label, created_at, activated_at, is_frozen)
        VALUES (%s, %s, %s, NOW(), NULL, FALSE)
        RETURNING id
    """, (current_user.id, code, f"SmartRiser {code}")).fetchone()
    asset_id = row['id']
    db.commit()

    # Create Order
    # Use 'smart_sign' type so webhook activates the asset
    order = Order(
        user_id=current_user.id,
        order_type='smart_sign', 
        status='pending',
        print_product=print_product,
        material=material,
        sides=sides,
        print_size=size,
        quantity=1,
        design_payload={'sign_asset_id': asset_id}
    )
    
    order.save() 
    
    # Stripe Session
    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price': price_id,
                'quantity': 1,
            }],
            mode='payment',
            success_url=url_for('orders.order_success', _external=True) + '?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=url_for('orders.order_cancel', _external=True),
            client_reference_id=str(order.id),
            metadata={
                'order_type': 'smart_sign',
                'order_id': order.id,
                'user_id': current_user.id,
                'sign_asset_id': asset_id
            }
        )
        return jsonify({'checkoutUrl': checkout_session.url})
    except Exception as e:
        logger.error(f"Stripe Checkout Error: {e}")
        return jsonify({'error': 'Payment initialization failed'}), 500
