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
        
    # Create Order via raw SQL (Option B True Strict: No asset yet)
    payload = {} # No sign_asset_id yet
    asset_id = None
    
    db = get_db()
    
    order_row = db.execute("""
        INSERT INTO orders (
            user_id, order_type, status, print_product, material, sides,
            print_size, quantity, design_payload
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (
        current_user.id, 'sign', 'pending_payment', print_product,
        material, sides, size, 1, Json(payload)
    )).fetchone()
    order_id = order_row['id']
    db.commit()
    
    # Stripe Session
    try:
        metadata = {
            'order_type': 'sign',
            'order_id': str(order_id),
            'user_id': str(current_user.id)
        }
        if asset_id is not None:
            metadata['sign_asset_id'] = str(asset_id)

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
            metadata=metadata
        )
        return jsonify({'checkoutUrl': checkout_session.url})
    except Exception as e:
        logger.error(f"Stripe Checkout Error: {e}")
        return jsonify({'error': 'Payment initialization failed'}), 500
