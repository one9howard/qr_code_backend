
from flask import Blueprint, request, jsonify, send_file, current_app, redirect, url_for
from flask_login import login_required, current_user
from database import get_db
from models import User
from services.listing_kits import create_or_get_kit, generate_kit
from services.stripe_checkout import create_checkout_attempt
from config import STRIPE_PRICE_LISTING_KIT
from utils.storage import get_storage

listing_kits_bp = Blueprint('listing_kits', __name__)

@listing_kits_bp.route('/api/kits', methods=['GET'])
@login_required
def list_kits():
    """List kits for user's properties."""
    db = get_db()
    # Join with properties to show even if kit record doesn't exist yet?
    # Or just list existing kits? Or list properties with kit status?
    # MVP: List user's properties and their kit status.
    
    properties = db.execute(
        """
        SELECT p.id, p.address, lk.id as kit_id, lk.status as kit_status
        FROM properties p
        JOIN agents a ON p.agent_id = a.id
        LEFT JOIN listing_kits lk ON lk.property_id = p.id
        WHERE a.user_id = %s
        ORDER BY p.created_at DESC
        """,
        (current_user.id,)
    ).fetchall()
    
    return jsonify([dict(row) for row in properties])

@listing_kits_bp.route('/api/kits/<int:property_id>/start', methods=['POST'])
@login_required
def start_kit(property_id):
    """
    Start kit generation.
    If Pro -> Generate immediately.
    If Not Pro -> Return Stripe Checkout URL.
    """
    db = get_db()
    
    # 1. Verify Ownership
    # Check if property belongs to user
    prop = db.execute(
        """
        SELECT p.id FROM properties p
        JOIN agents a ON p.agent_id = a.id
        WHERE p.id = %s AND a.user_id = %s
        """,
        (property_id, current_user.id)
    ).fetchone()
    
    if not prop:
        return jsonify({"error": "Property not found or unauthorized"}), 404
        
    # 2. Check Subscription / Entitlements
    # Kit purchase enables kit regeneration WITHOUT unlocking property
    from services.subscriptions import is_subscription_active
    from services.entitlements import has_paid_listing_kit
    
    is_pro = is_subscription_active(current_user.subscription_status)
    
    # Check if user has paid for listing_kit for this property
    # This is SEPARATE from property paid status (listing_kit does NOT unlock property)
    is_paid_for = has_paid_listing_kit(current_user.id, property_id)
    
    can_generate_freely = is_pro or is_paid_for
    
    kit = create_or_get_kit(current_user.id, property_id)
    
    if can_generate_freely:
        # Trigger Generation (Async)
        # BLOCKER FIX: Persist queued state immediately
        db.execute(
            "UPDATE listing_kits SET status='queued', last_error=NULL, updated_at=NOW() WHERE id=%s",
            (kit['id'],)
        )
        db.commit()

        current_app.logger.info(f"Enqueuing listing kit generation for kit {kit['id']} (Order validated)")
        from services.async_jobs import enqueue
        enqueue('generate_listing_kit', {'kit_id': kit['id'], 'user_id': current_user.id})
        
        return jsonify({"status": "queued", "kit_id": kit['id']})
    else:
        # Track upgrade prompt shown
        try:
            from services.events import track_event
            track_event(
                'upgrade_prompt_shown',
                user_id=current_user.id,
                property_id=property_id,
                meta={'reason': 'kit_not_purchased'}
            )
        except Exception:
            pass  # Best-effort tracking
        
        # Create Stripe Checkout
        # Price ID needs to be defined in config (STRIPE_PRICE_LISTING_KIT)
        # Using a fallback for now if env not set, though config should have it.
        price_id = STRIPE_PRICE_LISTING_KIT
        if not price_id or 'price_' not in price_id:
             # Return 402 with reason code if pricing not configured
             return jsonify({
                 "error": "upgrade_required",
                 "reason": "kit_not_purchased",
                 "message": "Purchase a Listing Kit for this property or upgrade to Pro."
             }), 402
             
        # Track kit checkout started
        try:
            from services.events import track_event
            track_event(
                'kit_checkout_started',
                user_id=current_user.id,
                property_id=property_id
            )
        except Exception:
            pass  # Best-effort tracking
             
        checkout_params = {
            "mode": "payment",
            "line_items": [{"price": price_id, "quantity": 1}],
            "metadata": {
                "user_id": current_user.id,
                "property_id": property_id,
                "purpose": "listing_kit"
            },
            "success_url": f"{request.host_url}dashboard?kit_success=true",
            "cancel_url": f"{request.host_url}dashboard"
        }
        
        # Create Order record first? 
        # Requirement D says: "Create order in orders table... Reuse checkout_attempt"
        # We need an order ID to track this.
        cursor = db.execute(
            """
            INSERT INTO orders (user_id, property_id, status, order_type, amount_total_cents, currency)
            VALUES (%s, %s, 'pending_payment', 'listing_kit', 0, 'usd')
            RETURNING id
            """,
            (current_user.id, property_id)
        )
        db.commit()
        order_id = cursor.fetchone()['id']
        
        checkout_params['metadata']['order_id'] = order_id
        
        attempt = create_checkout_attempt(current_user.id, "listing_kit", checkout_params, order_id)
        
        import stripe
        # stripe.api_key handled in app.py
        
        session = stripe.checkout.Session.create(**checkout_params)
        
        # Update attempt
        from services.stripe_checkout import update_attempt_status
        update_attempt_status(attempt['attempt_token'], 'session_created', stripe_session_id=session.id)
        
        return jsonify({"status": "payment_required", "checkout_url": session.url, "reason": "kit_not_purchased"})

@listing_kits_bp.route('/api/kits/<int:kit_id>/download', methods=['GET'])
@login_required
def download_kit(kit_id):
    """Download Kit ZIP."""
    db = get_db()
    
    # Verify Owner
    kit = db.execute(
        "SELECT * FROM listing_kits WHERE id = %s AND user_id = %s",
        (kit_id, current_user.id)
    ).fetchone()
    
    if not kit:
        return jsonify({"error": "Kit not found or unauthorized"}), 404 # Or 403
        
    if not kit['kit_zip_path']:
        return jsonify({"error": "Kit not ready"}), 400
        
    storage = get_storage()
    # Stream file
    # utils.storage abstraction usually has .get_file(key), returning BytesIO.
    
    file_bytes = storage.get_file(kit['kit_zip_path'])
    if not file_bytes:
        return jsonify({"error": "File missing"}), 404
    
    # Ensure pointer is at start
    file_bytes.seek(0)
    
    return send_file(
        file_bytes,
        download_name=f"listing_kit_{kit['property_id']}.zip",
        as_attachment=True,
        mimetype="application/zip"
    )
