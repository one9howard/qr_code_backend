"""
SmartRiser Routes

Checkout flow for SmartRiser products.
Currently behind feature flag.
"""
from flask import Blueprint, request, jsonify, render_template, redirect, url_for
from flask_login import login_required, current_user
from database import get_db
from services.print_catalog import get_price_id
from psycopg2.extras import Json
import stripe
import uuid
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

    # Create Order via raw SQL
    payload = {'sign_asset_id': asset_id}
    
    order_row = db.execute("""
        INSERT INTO orders (
            user_id, order_type, status, print_product, material, sides,
            print_size, quantity, design_payload
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (
        current_user.id, 'smart_sign', 'pending_payment', print_product,
        material, sides, size, 1, Json(payload)
    )).fetchone()
    order_id = order_row['id']
    db.commit()
    
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
            client_reference_id=str(order_id),
            metadata={
                'order_type': 'smart_sign',
                'order_id': order_id,
                'user_id': current_user.id,
                'sign_asset_id': asset_id
            }
        )
        return jsonify({'checkoutUrl': checkout_session.url})
    except Exception as e:
        logger.error(f"Stripe Checkout Error: {e}")
        return jsonify({'error': 'Payment initialization failed'}), 500
