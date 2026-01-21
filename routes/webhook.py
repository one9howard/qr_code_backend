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
from services.fulfillment import fulfill_order
from services.stripe_checkout import update_attempt_status
from constants import (
    ORDER_STATUS_PAID, 
    ORDER_STATUS_PENDING_PRODUCTION
)

webhook_bp = Blueprint('webhook', __name__)
stripe.api_key = STRIPE_SECRET_KEY

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
        traceback.print_exc()
        
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

def resolve_user_id(db, session):
    """
    Resolve local User ID from Stripe Session using multiple strategies.
    1. metadata.user_id
    2. client_reference_id
    3. customer_email / customer_details.email
    """
    # 1. Metadata
    user_id = session.get('metadata', {}).get('user_id')
    if user_id: 
        return user_id
        
    # 2. Client Reference ID
    if session.get('client_reference_id'):
        return session.get('client_reference_id')

    # 3. Email Fallback
    email = session.get('customer_email')
    if not email and session.get('customer_details'):
        email = session.get('customer_details').get('email')
        
    if email:
        user = db.execute("SELECT id FROM users WHERE email = %s", (email,)).fetchone()
        if user:
            current_app.logger.info(f"[Webhook] Resolved user {user['id']} via email {email}")
            return user['id']
            
    current_app.logger.warning(f"[Webhook] Failed to resolve user for session {session.get('id')}")
    return None

def handle_subscription_checkout(db, session):
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


def handle_payment_checkout(db, session):
    order_id = session.get('metadata', {}).get('order_id')
    
    # Just in case, try client_reference_id if metadata missing
    if not order_id and session.get('client_reference_id'):
        order_id = session.get('client_reference_id')

    if not order_id:
        current_app.logger.error("[Webhook] Error: No order_id in payment session")
        raise ValueError("No order_id in payment session metadata")

    # Extract payment details
    shipping = session.get('shipping_details') or session.get('customer_details')
    shipping_json = json.dumps(shipping) if shipping else None
    payment_intent = session.get('payment_intent')
    customer_id = session.get('customer')  # Stripe customer ID
    
    # Define paid_at before SQL
    paid_at = utc_iso()
    # Fetch current order state to determine updates
    # Use dict() safely with row objects
    row = db.execute("SELECT status, order_type, property_id FROM orders WHERE id = %s", (order_id,)).fetchone()
    if not row:
        current_app.logger.error(f"[Webhook] Order {order_id} not found during payment processing")
        raise ValueError(f"Order {order_id} not found")
        
    current_status = row['status']
    current_type = row['order_type']
    
    # 1. Determine Correct Order Type (Canonical)
    purpose = session.get('metadata', {}).get('purpose')
    
    if purpose == 'listing_unlock':
        target_type = 'listing_unlock'
    elif purpose == 'listing_kit':
        target_type = 'listing_kit'
    elif purpose == 'smart_sign':
        target_type = 'smart_sign'
    else:
        target_type = 'sign'
    
    final_type = current_type
    # Allow update if not yet a canonical final type
    if current_type not in ('sign', 'listing_unlock', 'smart_sign'):
        final_type = target_type
        
    # 2. Prevent Status Regression
    # If already fully processed (submitted/fulfilled), do NOT set back to 'paid'
    from constants import ORDER_STATUS_SUBMITTED_TO_PRINTER, ORDER_STATUS_FULFILLED
    new_status = ORDER_STATUS_PAID
    if current_status in (ORDER_STATUS_SUBMITTED_TO_PRINTER, ORDER_STATUS_FULFILLED):
        new_status = current_status
        current_app.logger.info(f"[Webhook] Order {order_id} is already {current_status}. Preserving status.")

    current_app.logger.info(f"[Webhook] Updating Order {order_id}: Status {current_status}->{new_status}, Type {current_type}->{final_type}")
    
    # --- STRICT PAYMENT CHECK (Option B) ---
    # Only activate/fulfill if definitive paid status
    payment_status = session.get('payment_status')
    if payment_status != 'paid':
        current_app.logger.warning(f"[Webhook] Session {session.get('id')} payment_status={payment_status}. Skipping activation/fulfillment.")
        # We still update metadata/email if available, but NOT status to PAID? 
        # Actually if it's not paid, we probably shouldn't even be here for 'checkout.session.completed' usually implies success,
        # but for delayed payment methods, it might be 'unpaid'. 
        # Safe strategy: Only proceed if 'paid'.
        return

    # Update order with payment information + fixed type + status
    # PHASE C: Capture Stripe Totals (amount_total_cents, currency)
    # session.amount_total is in cents
    db.execute('''
        UPDATE orders 
        SET status = %s, 
            order_type = %s,
            stripe_checkout_session_id = %s, 
            stripe_payment_intent_id = %s, 
            stripe_customer_id = %s,
            paid_at = %s, 
            shipping_address = %s,
            amount_total_cents = %s,
            currency = %s
        WHERE id = %s
    ''', (
        new_status,
        final_type,
        session.get('id'), 
        session.get('payment_intent'), 
        customer_id, 
        paid_at, 
        shipping_json, 
        session.get('amount_total'),  # Capture raw cents
        session.get('currency'),      # Capture currency code
        order_id
    ))
    db.commit()
    
    # Mark checkout attempt as completed (if present)
    attempt_token = session.get("metadata", {}).get("attempt_token")
    if attempt_token:
        try:
            update_attempt_status(attempt_token, "completed", stripe_customer_id=customer_id)
            current_app.logger.info(f"[Webhook] Marked attempt {attempt_token} as completed")
        except Exception as e:
            current_app.logger.warning(f"[Webhook] Could not update attempt {attempt_token}: {e}")

    # 3. Universal Entitlement Unlock
    # On successful paid checkout for both sign orders and listing unlocks, set properties.expires_at = NULL
    raw_property_id = session.get('metadata', {}).get('property_id')
    property_id = None

    # Prefer metadata (Stripe) when valid
    if isinstance(raw_property_id, int) and raw_property_id > 0:
        property_id = raw_property_id
    elif isinstance(raw_property_id, str):
        s = raw_property_id.strip()
        if s.isdigit():
            property_id = int(s)

    # Fallback: trust the persisted order row
    if not property_id:
        try:
            if row and row['property_id'] is not None:
                property_id = int(row['property_id'])
        except Exception:
            property_id = None

    if property_id:
        db.execute("UPDATE properties SET expires_at = NULL WHERE id = %s", (property_id,))
        db.commit()
        current_app.logger.info(f"[Webhook] Property {property_id} unlocked for Order {order_id} (expires_at=NULL).")

    # 4. SmartSign Activation (Idempotent)
    if final_type == 'smart_sign':
        asset_id = session.get('metadata', {}).get('sign_asset_id')
        if asset_id:
            # Check if already activated to avoid overwriting original activation time
            # or side-effects if we had them.
            existing = db.execute("SELECT activated_at FROM sign_assets WHERE id = %s", (asset_id,)).fetchone()
            if existing and existing['activated_at'] is None:
                db.execute("""
                    UPDATE sign_assets 
                    SET activated_at = CURRENT_TIMESTAMP,
                        activation_order_id = %s
                    WHERE id = %s
                """, (order_id, asset_id))
                db.commit()
                current_app.logger.info(f"[Webhook] Activated SmartSign Asset {asset_id} for Order {order_id}")
            else:
                current_app.logger.info(f"[Webhook] Asset {asset_id} already activated. Skipping.")

    # 5. Trigger Fulfillment (Idempotent)
    if final_type in ('sign', 'smart_sign'):
        # Check if print job already exists for this order
        existing_job = db.execute("SELECT job_id FROM print_jobs WHERE order_id = %s", (order_id,)).fetchone()
        
        if existing_job:
            current_app.logger.info(f"[Webhook] Print job already exists for Order {order_id}. Skipping fulfillment.")
        else:
            current_app.logger.info(f"[Webhook] Attempting fulfillment for Sign Order {order_id}...")
            try:
                if not fulfill_order(order_id):
                    # Fulfullment returned False (handled internal error)
                    current_app.logger.warning(f"[Webhook] Fulfillment returned False for Order {order_id}. Marked as failed.")
                else:
                    current_app.logger.info(f"[Webhook] Order {order_id} fulfilled logic complete.")
            except Exception as e:
                # Catch unexpected errors in fulfillment to protect the payment record
                current_app.logger.error(f"[Webhook] Fulfillment crashed for Order {order_id}: {e}")
                try:
                    # Ensure marked as failed
                    from constants import ORDER_STATUS_PRINT_FAILED
                    db.execute(
                        "UPDATE orders SET status = %s, fulfillment_error = %s WHERE id = %s",
                        (ORDER_STATUS_PRINT_FAILED, f"Webhook Fulfillment Crash: {str(e)}", order_id)
                    )
                    db.commit()
                except:
                    pass
    elif final_type == 'listing_kit':
        # 6. Trigger Listing Kit Generation (Idempotent)
        current_app.logger.info(f"[Webhook] Triggering Listing Kit generation for Order {order_id}...")
        try:
            from services.listing_kits import create_or_get_kit, generate_kit
            # Create/Get kit record
            # Use order user_id if possible, or resolve from somewhere?
            # Order row doesn't store user_id explicitly in this scope, but 'orders' table has user_id.
            order_row = db.execute("SELECT user_id, property_id FROM orders WHERE id = %s", (order_id,)).fetchone()
            if order_row:
                 kit = create_or_get_kit(order_row['user_id'], order_row['property_id'])
                 generate_kit(kit['id'])
                 current_app.logger.info(f"[Webhook] Kit {kit['id']} generated successfully.")
        except Exception as e:
            current_app.logger.error(f"[Webhook] Failed to generate kit for Order {order_id}: {e}")
            # Do not rollback payment processing; kit gen failure is non-fatal to payment
            pass
    else:
        current_app.logger.info(f"[Webhook] Order {order_id} is type '{final_type}'. Skipping physical fulfillment.")

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
    
    cursor = db.execute('''
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
            WHERE status = 'paid' AND order_type IN ('sign', 'listing_unlock', 'smart_sign')
        )
    ''', (now_iso, stripe_customer_id))
    
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
