import stripe
import traceback
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from config import (
    STRIPE_SECRET_KEY, STRIPE_PRICE_MONTHLY, STRIPE_PRICE_ANNUAL, 
    STRIPE_SUCCESS_URL, STRIPE_CANCEL_URL, STRIPE_PORTAL_RETURN_URL
)
from services.stripe_checkout import (
    create_checkout_attempt,
    get_checkout_attempt,
    update_attempt_status,
    validate_attempt_params
)
from services.stripe_config import get_configured_prices, get_unlock_price_id
from datetime import datetime
from database import get_db

billing_bp = Blueprint('billing', __name__)
# stripe.api_key handled in app.py

@billing_bp.route("/billing")
@login_required
def index():
    """Render subscription options."""
    # Check grace period/active status
    is_active = current_user.is_pro
    
    # Fetch dynamic prices
    prices = get_configured_prices()
    
    return render_template("billing.html", is_active=is_active, prices=prices)

@billing_bp.route("/billing/checkout", methods=["POST"])
@login_required
def checkout():
    """
    Create Stripe Checkout Session for Subscription.
    
    Implements attempt-based idempotency:
    - Each new checkout creates a unique attempt with its own idempotency key
    - Retries with the same attempt_token return the existing session
    - Parameter changes with same attempt_token create a new attempt
    """
    price_id = request.form.get('price_id')
    attempt_token = request.form.get('attempt_token')
    
    if price_id not in [STRIPE_PRICE_MONTHLY, STRIPE_PRICE_ANNUAL]:
        flash("Invalid price selection.", "error")
        return redirect(url_for('billing.index'))
    
    try:
        # Build checkout params (without idempotency_key - that comes from attempt)
        checkout_params = {
            'line_items': [{'price': price_id, 'quantity': 1}],
            'mode': 'subscription',
            'success_url': STRIPE_SUCCESS_URL,
            'cancel_url': STRIPE_CANCEL_URL,
            'client_reference_id': str(current_user.id),
            'subscription_data': {
                "metadata": {"user_id": str(current_user.id)}
            }
        }
        
        if current_user.stripe_customer_id:
            checkout_params['customer'] = current_user.stripe_customer_id
        else:
            checkout_params['customer_email'] = current_user.email
        
        attempt = None
        
        # Check if we have an existing attempt to reuse
        if attempt_token:
            attempt = get_checkout_attempt(attempt_token)
            
            if attempt:
                # If session already created, return that session
                if attempt.get('stripe_session_id'):
                    try:
                        existing_session = stripe.checkout.Session.retrieve(
                            attempt['stripe_session_id']
                        )
                        # Only reuse if session is still valid (not expired/completed)
                        if existing_session.status in ('open',):
                            current_app.logger.info(f"[Billing] Reusing existing session {existing_session.id}")
                            return redirect(existing_session.url, code=303)
                    except stripe.error.InvalidRequestError:
                        # Session no longer valid, create new attempt
                        current_app.logger.info(f"[Billing] Session {attempt['stripe_session_id']} no longer valid")
                        attempt = None
                
                # Validate params match - if not, create new attempt
                if attempt and not validate_attempt_params(attempt, checkout_params):
                    current_app.logger.info(f"[Billing] Params changed for attempt {attempt_token}, creating new attempt")
                    attempt = None
        
        # Create new attempt if needed
        if not attempt:
            attempt = create_checkout_attempt(
                user_id=current_user.id,
                purpose='subscription_upgrade',
                params=checkout_params
            )
            current_app.logger.info(f"[Billing] Created new attempt {attempt['attempt_token']}")
        
        # Add metadata with attempt_token for webhook tracking
        checkout_params['metadata'] = {
            'user_id': str(current_user.id),
            'attempt_token': attempt['attempt_token'],
            'purpose': 'subscription_upgrade'
        }
        
        # Create Stripe Checkout Session with attempt's idempotency key
        checkout_session = stripe.checkout.Session.create(
            **checkout_params,
            idempotency_key=attempt['idempotency_key']
        )
        
        # Update attempt with session info
        update_attempt_status(
            attempt['attempt_token'],
            'session_created',
            stripe_session_id=checkout_session.id
        )
        
        # --- Track Event ---
        from services.events import track_event
        plan_name = 'pro'
        interval = 'unknown'
        if price_id == STRIPE_PRICE_MONTHLY: interval = 'month'
        elif price_id == STRIPE_PRICE_ANNUAL: interval = 'year'
        
        track_event(
            "checkout_started",
            source="server",
            user_id=current_user.id,
            payload={
                "plan": plan_name,
                "interval": interval,
                "price_id": price_id,
                "session_id": checkout_session.id
            }
        )
        
        current_app.logger.info(f"[Billing] Created session {checkout_session.id} for attempt {attempt['attempt_token']}")
        return redirect(checkout_session.url, code=303)
        
    except stripe.error.IdempotencyError as e:
        # Idempotency collision - should be rare with our approach
        current_app.logger.error(f"[Billing] Idempotency error: {e}")
        traceback.print_exc()
        if attempt:
            update_attempt_status(attempt['attempt_token'], 'failed', error_message=str(e))
        flash("Please try again.", "error")
        return redirect(url_for('billing.index'))
        
    except stripe.error.StripeError as e:
        current_app.logger.error(f"[Billing] Stripe error: {e}")
        traceback.print_exc()
        if attempt:
            update_attempt_status(attempt['attempt_token'], 'failed', error_message=str(e))
        flash(f"Error creating checkout session: {str(e)}", "error")
        return redirect(url_for('billing.index'))
        
    except Exception as e:
        current_app.logger.error(f"[Billing] Unexpected error: {e}")
        traceback.print_exc()
        if attempt:
            update_attempt_status(attempt['attempt_token'], 'failed', error_message=str(e))
        flash("An unexpected error occurred. Please try again.", "error")
        return redirect(url_for('billing.index'))



@billing_bp.route("/billing/portal")
@login_required
def portal():
    """Redirect to Stripe Customer Portal."""
    if not current_user.stripe_customer_id:
        flash("No billing account found.", "error")
        return redirect(url_for('billing.index'))

    try:
        portal_session = stripe.billing_portal.Session.create(
            customer=current_user.stripe_customer_id,
            return_url=STRIPE_PORTAL_RETURN_URL,
        )
        return redirect(portal_session.url, code=303)
    except Exception as e:
        flash(f"Error accessing portal: {str(e)}", "error")
        return redirect(url_for('dashboard.index'))

@billing_bp.route("/billing/unlock-listing/<int:property_id>", methods=["POST"])
@login_required
def unlock_listing_checkout(property_id):
    """
    Create Checkout Session for Listing Unlock (One-time).
    """
    db = get_db()
    # 1. Verify Ownership
    row = db.execute(
        "SELECT 1 FROM properties WHERE id = %s AND agent_id IN (SELECT id FROM agents WHERE user_id = %s)", 
        (property_id, current_user.id)
    ).fetchone()
    
    if not row:
        flash("Property not found or access denied.", "error")
        return redirect(url_for('dashboard.index'))
        
    price_id = get_unlock_price_id()
    if not price_id:
        flash("Listing unlock feature is not configured.", "error")
        return redirect(url_for('dashboard.index'))
        
    try:
        # 2. Create 'listing_unlock' Order
        # RETURNING id replacement
        cursor = db.execute('''
            INSERT INTO orders (
                user_id, property_id, status, order_type, 
                created_at
            ) VALUES (%s, %s, 'pending_payment', 'listing_unlock', CURRENT_TIMESTAMP)
            RETURNING id
        ''', (current_user.id, property_id))
        order_id = cursor.fetchone()['id']
        db.commit()
        
        # 3. Create Stripe Checkout
        checkout_params = {
            'line_items': [{'price': price_id, 'quantity': 1}],
            'mode': 'payment',  # One-time payment
            'success_url': STRIPE_SUCCESS_URL,
            'cancel_url': STRIPE_CANCEL_URL,
            'client_reference_id': str(current_user.id),
            'metadata': {
                'order_id': str(order_id),
                'purpose': 'listing_unlock',
                'property_id': str(property_id) 
            }
        }
        
        if current_user.stripe_customer_id:
            checkout_params['customer'] = current_user.stripe_customer_id
        else:
            checkout_params['customer_email'] = current_user.email
            
        # Create attempt
        attempt = create_checkout_attempt(
            user_id=current_user.id,
            purpose='listing_unlock',
            params=checkout_params,
            order_id=order_id
        )
        
        # Add attempt_token to metadata
        checkout_params['metadata']['attempt_token'] = attempt['attempt_token']
        
        # Create Session
        checkout_session = stripe.checkout.Session.create(
            **checkout_params,
            idempotency_key=attempt['idempotency_key']
        )
        
        # Record session
        update_attempt_status(attempt['attempt_token'], 'session_created', stripe_session_id=checkout_session.id)
        
        # Update order with session id
        db.execute("UPDATE orders SET stripe_checkout_session_id = %s WHERE id = %s", (checkout_session.id, order_id))
        db.commit()
        
        return redirect(checkout_session.url, code=303)
        
    except Exception as e:
        current_app.logger.error(f"[Billing] Unlock Listing Error: {e}")
        traceback.print_exc()
        flash("Error creating payment session.", "error")
        return redirect(url_for('dashboard.index'))

@billing_bp.route("/billing/success")
@login_required
def success():
    """
    Billing Success Page - READ-ONLY.
    
    This page verifies payment status for display purposes only.
    All subscription activation and state mutation is handled exclusively
    by webhooks. No DB writes occur here.
    """
    session_id = request.args.get('session_id')
    
    # Simple success default
    status_message = "Payment successful! Your account will be updated momentarily."
    
    if session_id:
        try:
            # Read-only verification: Check Stripe directly for display
            session = stripe.checkout.Session.retrieve(session_id)
            
            # Verify it belongs to this user (security)
            is_own_session = False
            if session.client_reference_id == str(current_user.id):
                is_own_session = True
            elif session.metadata and session.metadata.get('user_id') == str(current_user.id):
                is_own_session = True
            elif session.customer_email == current_user.email:
                is_own_session = True
                
            if is_own_session and session.payment_status == 'paid':
                purpose = session.metadata.get('purpose') if session.metadata else None
                
                if purpose == 'listing_unlock':
                    status_message = "Listing unlock confirmed! It will be active within moments."
                    current_app.logger.info(f"[Billing] Success Page: Listing Unlock Session {session.id} verified as paid.")
                else:
                    # Default: Subscription Upgrade
                    current_app.logger.info(f"[Billing] Success Page: Subscription Session {session.id} verified as paid.")
                    status_message = "Subscription confirmed! You are now a Pro member."
                
        except Exception as e:
            current_app.logger.error(f"[Billing] Verification failed: {e}")
            # Don't show error to user, just load success page.

    return render_template("billing_success.html", message=status_message)

@billing_bp.route("/billing/start", methods=["GET"])
@login_required
def start():
    """
    GET route to initiate Stripe Checkout (for use in links).
    Redirects to Stripe Checkout Session.
    """
    plan = request.args.get('plan')
    
    price_id = None
    if plan == 'monthly':
        price_id = STRIPE_PRICE_MONTHLY
    elif plan == 'annual':
        price_id = STRIPE_PRICE_ANNUAL
        
    if not price_id:
        flash("Invalid plan selected.", "error")
        return redirect(url_for('billing.index'))
        
    try:
        # Build checkout params
        checkout_params = {
            'line_items': [{'price': price_id, 'quantity': 1}],
            'mode': 'subscription',
            'success_url': STRIPE_SUCCESS_URL,
            'cancel_url': STRIPE_CANCEL_URL,
            'client_reference_id': str(current_user.id),
            'subscription_data': {
                "metadata": {"user_id": str(current_user.id)}
            }
        }
        
        if current_user.stripe_customer_id:
            checkout_params['customer'] = current_user.stripe_customer_id
        else:
            checkout_params['customer_email'] = current_user.email

        # Create attempt (reuse service logic)
        attempt = create_checkout_attempt(
            user_id=current_user.id,
            purpose='subscription_upgrade',
            params=checkout_params
        )
        
        # Add metadata (both top-level and subscription-specific for safety)
        checkout_params['metadata'] = {
            'user_id': str(current_user.id),
            'attempt_token': attempt['attempt_token'],
            'purpose': 'subscription_upgrade'
        }
        checkout_params['subscription_data']['metadata']['attempt_token'] = attempt['attempt_token']
        checkout_params['subscription_data']['metadata']['purpose'] = 'subscription_upgrade'
        
        # Create session
        checkout_session = stripe.checkout.Session.create(
            **checkout_params,
            idempotency_key=attempt['idempotency_key']
        )
        
        update_attempt_status(
            attempt['attempt_token'],
            'session_created',
            stripe_session_id=checkout_session.id
        )
        
        return redirect(checkout_session.url, code=303)
        
    except Exception as e:
        current_app.logger.error(f"[Billing] Start error: {e}")
        traceback.print_exc()
        flash("Error starting checkout. Please try again.", "error")
        return redirect(url_for('billing.index'))

@billing_bp.route("/billing/cancel")
def cancel():
    flash("Subscription cancelled or payment failed.", "info")
    if current_user.is_authenticated:
        return redirect(url_for('billing.index'))
    return redirect(url_for('public.landing'))
