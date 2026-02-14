#!/usr/bin/env python3
"""
Reconcile Stuck Orders Script

Finds orders that are stuck in 'pending_payment' but Stripe says they're paid.
This handles cases where webhook delivery failed.

Usage:
    python scripts/reconcile_stuck_orders.py [--dry-run] [--hours N]

Options:
    --dry-run   Print what would be repaired without making changes
    --hours N   Look back N hours (default: 24)
"""
import os
import sys
import argparse
from datetime import UTC, datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import stripe
from database import get_db
from config import STRIPE_SECRET_KEY

stripe.api_key = STRIPE_SECRET_KEY


def find_stuck_orders(db, hours_back=24):
    """
    Find orders stuck in pending_payment for more than X hours.
    These are candidates for reconciliation.
    """
    cutoff = datetime.now(UTC) - timedelta(hours=hours_back)
    
    orders = db.execute("""
        SELECT id, stripe_checkout_session_id, status, created_at, order_type
        FROM orders 
        WHERE status = 'pending_payment'
        AND created_at < %s
        AND stripe_checkout_session_id IS NOT NULL
        ORDER BY created_at ASC
    """, (cutoff,)).fetchall()
    
    return orders


def check_stripe_session(session_id):
    """
    Check Stripe for the real payment status of a session.
    Returns: ('paid', session_obj) or ('unpaid', None) or ('error', error_msg)
    """
    try:
        session = stripe.checkout.Session.retrieve(session_id)
        if session.payment_status == 'paid':
            return ('paid', session)
        return ('unpaid', None)
    except stripe.error.InvalidRequestError as e:
        return ('error', str(e))
    except Exception as e:
        return ('error', str(e))


def repair_order(db, order_id, stripe_session):
    """
    Repair a stuck order by processing it as paid.
    """
    from services.orders import process_paid_order
    
    # Convert Stripe session to dict for process_paid_order
    session_dict = {
        'id': stripe_session.id,
        'metadata': dict(stripe_session.metadata) if stripe_session.metadata else {},
        'payment_status': stripe_session.payment_status,
        'payment_intent': stripe_session.payment_intent,
        'customer': stripe_session.customer,
        'shipping_details': stripe_session.shipping_details,
        'customer_details': stripe_session.customer_details,
        'amount_total': stripe_session.amount_total,
        'currency': stripe_session.currency,
        'client_reference_id': stripe_session.client_reference_id,
    }
    
    # Ensure order_id is in metadata
    if 'order_id' not in session_dict['metadata']:
        session_dict['metadata']['order_id'] = str(order_id)
    
    try:
        process_paid_order(db, session_dict)
        return True
    except Exception as e:
        print(f"  ERROR repairing order {order_id}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description='Reconcile stuck orders with Stripe')
    parser.add_argument('--dry-run', action='store_true', help='Print what would be done without changes')
    parser.add_argument('--hours', type=int, default=24, help='Look back N hours (default: 24)')
    args = parser.parse_args()
    
    print(f"=== Stuck Order Reconciliation ===")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    print(f"Looking back: {args.hours} hours")
    print()
    
    # Need Flask app context for database
    from app import create_app
    app = create_app()
    
    with app.app_context():
        db = get_db()
        
        # Find stuck orders
        stuck_orders = find_stuck_orders(db, args.hours)
        print(f"Found {len(stuck_orders)} stuck orders in 'pending_payment'")
        print()
        
        repaired = 0
        skipped = 0
        errors = 0
        
        for order in stuck_orders:
            order_id = order['id']
            session_id = order['stripe_checkout_session_id']
            created = order['created_at']
            order_type = order['order_type']
            
            print(f"Order {order_id} ({order_type}, created {created})")
            print(f"  Stripe Session: {session_id}")
            
            # Check Stripe
            status, session = check_stripe_session(session_id)
            
            if status == 'paid':
                print(f"  Stripe says: PAID ✓")
                if args.dry_run:
                    print(f"  [DRY RUN] Would repair this order")
                    repaired += 1
                else:
                    if repair_order(db, order_id, session):
                        print(f"  REPAIRED ✓")
                        repaired += 1
                    else:
                        print(f"  REPAIR FAILED ✗")
                        errors += 1
            elif status == 'unpaid':
                print(f"  Stripe says: unpaid (session may have expired)")
                skipped += 1
            else:
                print(f"  Stripe error: {session}")
                errors += 1
            
            print()
        
        print("=== Summary ===")
        print(f"Total stuck orders: {len(stuck_orders)}")
        print(f"Repaired: {repaired}")
        print(f"Skipped (unpaid): {skipped}")
        print(f"Errors: {errors}")
        
        if args.dry_run and repaired > 0:
            print()
            print("Run without --dry-run to apply repairs")


if __name__ == '__main__':
    main()
