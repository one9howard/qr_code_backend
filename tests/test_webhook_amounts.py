import pytest
from unittest.mock import patch
from routes.webhook import handle_payment_checkout

def test_webhook_captures_totals(db):
    """Webhook should capture amount_total and currency."""
    # 1. Setup Data with Constraints
    # User
    user_id = db.execute(
        "INSERT INTO users (email, password_hash, is_verified, is_admin) VALUES (%s, %s, %s, %s) RETURNING id", 
        ('webhook_test@example.com', 'hash', True, False)
    ).fetchone()['id']
    
    # Agent
    agent_id = db.execute(
        "INSERT INTO agents (user_id, name, brokerage, email, phone) VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (user_id, 'Webhook Agent', 'Brokerage', 'agent@webhook.com', '555-1234')
    ).fetchone()['id']
                          
    # Property
    prop_id = db.execute(
        "INSERT INTO properties (agent_id, address, beds, baths, slug, qr_code) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
        (agent_id, '123 Webhook Ln', 3, 2, 'webhook-slug', 'webhook-qr')
    ).fetchone()['id']
                         
    # Order (Initial)
    order_id = db.execute(
        "INSERT INTO orders (user_id, property_id, status, order_type) VALUES (%s, %s, %s, %s) RETURNING id",
        (user_id, prop_id, 'pending_payment', 'sign')
    ).fetchone()['id']
    db.commit()

    # 2. Mock Stripe Session
    session = {
        'id': 'cs_test_webhook_123',
        'metadata': {'order_id': str(order_id), 'purpose': 'sign'},
        'amount_total': 5000, 
        'payment_status': 'paid',
        'currency': 'usd'
    }
    
    # 3. Call handler with patch
    # Patching 'routes.webhook.fulfill_order' because that is where it is imported/used
    with patch('routes.webhook.fulfill_order', return_value=True) as mock_fulfill:
        handle_payment_checkout(db, session)
        
    # 4. Verify DB Update
    # We check on the same connection, so we should see uncommitted changes if any, 
    # but the webhook handler likely commits.
    order = db.execute(
        "SELECT amount_total_cents, currency, status, stripe_checkout_session_id FROM orders WHERE id=%s", 
        (order_id,)
    ).fetchone()
    
    assert order['amount_total_cents'] == 5000
    assert order['currency'] == 'usd'
    assert order['status'] == 'paid'
    assert order['stripe_checkout_session_id'] == 'cs_test_webhook_123'
