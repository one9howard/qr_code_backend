import stripe
import json
import traceback
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
from flask_login import current_user
from config import STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET
from utils.timestamps import utc_iso
from database import get_db
from models import User
from services.stripe_checkout import update_attempt_status
from constants import (
    ORDER_STATUS_PAID, 
    ORDER_STATUS_PENDING_PRODUCTION
)

webhook_bp = Blueprint('webhook', __name__)
# stripe.api_key handled in app.py

@webhook_bp.route("/stripe/webhook", methods=["POST"])
def stripe_webhook():
    # Early-exit if webhook secret is not configured
    # This surfaces misconfig quickly instead of cryptic signature errors
    if not STRIPE_WEBHOOK_SECRET:
        current_app.logger.error(
            "[Webhook] STRIPE_WEBHOOK_SECRET is not configured. "
            "Check your .env file and ensure the value is set correctly."
        )
        return jsonify({"error": "Webhook not configured"}), 500

    payload = request.get_data()
    sig_header = request.headers.get('Stripe-Signature')

    # 1. Validate Signature
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        current_app.logger.warning(f"[Webhook] Invalid payload: {e}")
        return jsonify({"error": "Invalid payload"}), 400
    except stripe.error.SignatureVerificationError as e:
        current_app.logger.warning(f"[Webhook] Invalid signature: {e}")
        return jsonify({"error": "Invalid signature"}), 400

    db = get_db()
    event_type = event['type']
    event_id = event['id']
    
    current_app.logger.info(f"[Webhook] Received event: {event_type} (ID: {event_id})")

    # 2. Status-Based Idempotency Check with Concurrency Safety
    # Strategy: Insert (if new) -> Claim (atomic update) -> Process
    
    # Step A: Ensure event exists in DB
    try:
        db.execute(
            """INSERT INTO stripe_events (event_id, type, status, created_at, updated_at) 
               VALUES (%s, %s, 'received', %s, %s)""",
            (event_id, event_type, utc_iso(), utc_iso())
        )
        db.commit()
    except Exception:
        # Ignore insert errors (likely unique constraint violation if exists)
        # We process a rollback to clear the aborted transaction state
        db.rollback()
        # We proceed to try claiming it.
        pass

    # Step B: Atomically Claim the Event
    # Only transition from 'received' or 'failed' to 'processing'
    cursor = db.execute(
        """UPDATE stripe_events 
           SET status = 'processing', updated_at = %s 
           WHERE event_id = %s AND status IN ('received', 'failed')""",
        (utc_iso(), event_id)
    )
    db.commit()

    if cursor.rowcount == 0:
        # Could not claim. Either:
        # 1. Already 'processing' (other worker)
        # 2. Already 'processed' (done)
        # 3. Does not exist (shouldn't happen due to Step A)
        
        # Check current status for logging
        existing = db.execute("SELECT status FROM stripe_events WHERE event_id = %s", (event_id,)).fetchone()
        status = existing['status'] if existing else 'unknown'
        
        current_app.logger.info(f"[Webhook] Event {event_id} skipped. Status: {status} (Note: idempotent_concurrent)")
        return jsonify({"status": "success", "note": "idempotent_concurrent"}), 200

    # Step C: Proceed to processing (we hold the lock)


    # 3. Process Event - Return 5xx on failure to trigger Stripe retry
    try:
        if event_type == 'checkout.session.completed':
            session = event['data']['object']
            mode = session.get('mode')
            if mode == 'subscription':
                handle_subscription_checkout(db, session)
            elif mode == 'payment':
                handle_payment_checkout(db, session)
                
        elif event_type == 'invoice.paid':
            invoice = event['data']['object']
            handle_invoice_paid(db, invoice)
            
        elif event_type == 'customer.subscription.updated':
            subscription = event['data']['object']
            handle_subscription_updated(db, subscription)

        elif event_type == 'customer.subscription.deleted':
            subscription = event['data']['object']
            handle_subscription_deleted(db, subscription)
        
        # SUCCESS - Mark as processed
        db.execute(
            """UPDATE stripe_events SET status = 'processed', last_error = NULL, updated_at = %s 
               WHERE event_id = %s""",
            (utc_iso(), event_id)
        )
        db.commit()
        current_app.logger.info(f"[Webhook] Event {event_id} processed successfully.")
            
    except Exception as e:
        current_app.logger.error(f"[Webhook] ERROR processing {event_type}: {e}")
        current_app.logger.exception(f"[Webhook] Exception details:")
        
        # FAILURE - Mark as failed so Stripe retry will reprocess
        try:
            db.execute(
                """UPDATE stripe_events SET status = 'failed', last_error = %s, updated_at = %s 
                   WHERE event_id = %s""",
                (str(e)[:500], utc_iso(), event_id)
            )
            db.commit()
        except Exception as db_err:
            current_app.logger.error(f"[Webhook] Failed to update event status: {db_err}")
        
        # Return 500 to trigger Stripe retry
        return jsonify({"error": "Internal processing error", "event_id": event_id}), 500
        
    return jsonify({"status": "success"}), 200

def handle_subscription_checkout(db, session):
    from services.orders import resolve_user_id
    user_id = resolve_user_id(db, session)
    if not user_id:
        current_app.logger.warning(f"[Webhook] Skipping subscription checkout: Unresolved user.")
        return

    customer_id = session.get('customer')
    subscription_id = session.get('subscription')
    
    # Mark checkout attempt as completed (if present)
    attempt_token = session.get('metadata', {}).get('attempt_token')
    if attempt_token:
        try:
            update_attempt_status(
                attempt_token, 
                'completed', 
                stripe_customer_id=customer_id
            )
            current_app.logger.info(f"[Webhook] Marked attempt {attempt_token} as completed")
        except Exception as e:
            current_app.logger.warning(f"[Webhook] Warning: Could not update attempt {attempt_token}: {e}")
    else:
        current_app.logger.info(f"[Webhook] No attempt_token in metadata (legacy session)")
    
    # Default status if retrieval fails
    status = 'active'
    end_date_iso = None

    # Try to retrieve fresh subscription details
    try:
        sub = stripe.Subscription.retrieve(subscription_id)
        status = getattr(sub, 'status', 'active')
        current_period_end = getattr(sub, 'current_period_end', None)
        if current_period_end:
            end_date_iso = datetime.fromtimestamp(current_period_end).isoformat()
    except Exception as e:
        current_app.logger.warning(f"[Webhook] Warning: Could not retrieve subscription {subscription_id}: {e}")
        # Continue with defaults to ensure mapping exists

    current_app.logger.info(f"[Webhook] Linking User {user_id} -> Cust {customer_id}, Sub {subscription_id}, Status {status}")

    db.execute('''
        UPDATE users 
        SET stripe_customer_id = %s, 
            stripe_subscription_id = %s,
            subscription_status = %s, 
            subscription_end_date = %s 
        WHERE id = %s
    ''', (customer_id, subscription_id, status, end_date_iso, user_id))
    db.commit()
    
    # --- Track Event ---
    from services.events import track_event
    track_event(
        "subscription_activated",
        source="server",
        user_id=user_id,
        payload={
            "stripe_subscription_id": subscription_id,
            "status": status,
            "session_id": session.get('id')
        }
    )


def handle_payment_checkout(db, session):
    """
    Delegate payment processing to Service Layer.
    This logic is now shared with /order/success route for redundancy.
    """
    from services.orders import process_paid_order
    try:
        process_paid_order(db, session)
    except Exception as e:
        current_app.logger.error(f"[Webhook] Error processing paid order: {e}")
        raise e  # Re-raise to trigger webhook failure/retry

def handle_invoice_paid(db, invoice):
    customer_id = invoice.get('customer')
    subscription_id = invoice.get('subscription')
    
    if not customer_id:
        return

    end_date_iso = None
    try:
        if subscription_id:
            sub = stripe.Subscription.retrieve(subscription_id)
            current_period_end = getattr(sub, 'current_period_end', None)
            if current_period_end:
                end_date_iso = datetime.fromtimestamp(current_period_end).isoformat()
    except Exception as e:
         current_app.logger.warning(f"[Webhook] Error retrieving subscription for invoice: {e}")

    # Update User Status
    # Fallback to update by subscription_id if we have it recorded
    updated = False
    if subscription_id:
        cursor = db.execute('''
            UPDATE users SET subscription_status = 'active', subscription_end_date = %s 
            WHERE stripe_subscription_id = %s
        ''', (end_date_iso, subscription_id))
        if cursor.rowcount > 0:
            updated = True
            current_app.logger.info(f"[Webhook] Invoice paid: Updated via Subscription ID {subscription_id}")

    if not updated:
        # Fallback to customer_id
        db.execute('''
            UPDATE users SET subscription_status = 'active', subscription_end_date = %s 
            WHERE stripe_customer_id = %s
        ''', (end_date_iso, customer_id))
        current_app.logger.info(f"[Webhook] Invoice paid: Updated via Customer ID {customer_id}")
    
    db.commit()
    
    # Unfreeze SmartSigns since invoice paid implies active status
    _set_sign_assets_frozen_for_customer(db, customer_id, frozen=False)


def handle_subscription_updated(db, subscription):
    sub_id = subscription.get('id')
    customer_id = subscription.get('customer')
    status = subscription.get('status')
    current_period_end = subscription.get('current_period_end')
    
    end_date_iso = None
    if current_period_end:
        end_date_iso = datetime.fromtimestamp(current_period_end).isoformat()

    current_app.logger.info(f"[Webhook] Subscription updated: {sub_id} -> {status}")

    # Try update by ID
    cursor = db.execute('''
        UPDATE users 
        SET subscription_status = %s, subscription_end_date = %s
        WHERE stripe_subscription_id = %s
    ''', (status, end_date_iso, sub_id))
    
    if cursor.rowcount == 0:
        # Fallback to customer ID if subscription ID wasn't linked yet
        db.execute('''
            UPDATE users 
            SET subscription_status = %s, subscription_end_date = %s, stripe_subscription_id = %s
            WHERE stripe_customer_id = %s
        ''', (status, end_date_iso, sub_id, customer_id))
    
    db.commit()
    
    # 2. Check for Freeze (if status changed to non-active)
    # We treat 'active' and 'trialing' as active. Everything else (unpaid, canceled, incomplete_expired, past_due?) is frozen.
    active_states = ('active', 'trialing')
    should_be_active = status in active_states
    
    if not should_be_active:
        # Freeze Properties (Expiration Logic)
        _freeze_properties_for_customer(db, customer_id)
        
    # SmartSign Freeze Logic (Subscription-based)
    # If active, ensure frozen=False. If inactive, ensure frozen=True.
    _set_sign_assets_frozen_for_customer(db, customer_id, frozen=not should_be_active)

def handle_subscription_deleted(db, subscription):
    sub_id = subscription.get('id')
    customer_id = subscription.get('customer')
    current_app.logger.info(f"[Webhook] Subscription deleted: {sub_id}")
    
    db.execute('''
        UPDATE users SET subscription_status = 'canceled'
        WHERE stripe_subscription_id = %s OR stripe_customer_id = %s
    ''', (sub_id, customer_id))
    db.commit()
    
    # Freeze immediately
    _freeze_properties_for_customer(db, customer_id)
    _set_sign_assets_frozen_for_customer(db, customer_id, frozen=True)

def _freeze_properties_for_customer(db, stripe_customer_id):
    """
    Freeze all properties for a user that are NOT backed by a paid order.
    Executed when subscription ends.
    """
    if not stripe_customer_id:
        return

    current_app.logger.info(f"[Webhook] Freezing unpaid properties for customer {stripe_customer_id}...")
    
    from utils.timestamps import utc_iso
    now_iso = utc_iso()
    
    from constants import PAID_STATUSES
    
    # Canonical Freeze Logic (Blocker Fix)
    placeholders = ','.join(['%s'] * len(PAID_STATUSES))
    
    # Query must exclude properties that have a PAID order of valid types
    
    query = f'''
        UPDATE properties 
        SET expires_at = %s 
        WHERE id IN (
            SELECT p.id 
            FROM properties p
            JOIN agents a ON p.agent_id = a.id
            JOIN users u ON a.user_id = u.id
            WHERE u.stripe_customer_id = %s
        )
        AND id NOT IN (
            SELECT property_id FROM orders 
            WHERE status IN ({placeholders}) 
            AND order_type IN ('sign', 'listing_unlock', 'smart_sign')
        )
    '''
    
    # Params: [expires_at_val, stripe_cust_id, *PAID_STATUSES]
    params = [now_iso, stripe_customer_id] + list(PAID_STATUSES)
    
    cursor = db.execute(query, tuple(params))
    
    if cursor.rowcount > 0:
        db.commit()
        current_app.logger.info(f"[Webhook] Frozen {cursor.rowcount} properties for customer {stripe_customer_id}")
    else:
        current_app.logger.info(f"[Webhook] No properties needed freezing for customer {stripe_customer_id}")

def _set_sign_assets_frozen_for_customer(db, stripe_customer_id, frozen):
    """
    Update is_frozen status for all SmartSigns owned by this customer.
    """
    if not stripe_customer_id:
        return
        
    action = "Freezing" if frozen else "Unfreezing"
    current_app.logger.info(f"[Webhook] {action} SmartSigns for customer {stripe_customer_id}...")
    
    cursor = db.execute("""
        UPDATE sign_assets
        SET is_frozen = %s, updated_at = now()
        WHERE user_id IN (
            SELECT id FROM users WHERE stripe_customer_id = %s
        )
    """, (frozen, stripe_customer_id))
    
    if cursor.rowcount > 0:
        db.commit()
        current_app.logger.info(f"[Webhook] Updated {cursor.rowcount} SmartSigns (is_frozen={frozen}) for customer {stripe_customer_id}")
    else:
        current_app.logger.info(f"[Webhook] No SmartSigns found to update for customer {stripe_customer_id}")
