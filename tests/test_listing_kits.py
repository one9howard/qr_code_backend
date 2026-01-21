
import pytest
import io
import os
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone
from werkzeug.security import generate_password_hash

# --- Fixtures ---

@pytest.fixture
def kit_data(client, db):
    """Setup data for kit logic."""
    # User (Pro & Non-Pro)
    hashed_pw = generate_password_hash('hash')
    pro_id = db.execute(
        "INSERT INTO users (email, password_hash, is_verified, subscription_status) VALUES (%s, %s, %s, 'active') RETURNING id",
        ('pro@kit.com', hashed_pw, True)
    ).fetchone()['id']
    
    basic_id = db.execute(
        "INSERT INTO users (email, password_hash, is_verified, subscription_status) VALUES (%s, %s, %s, 'inactive') RETURNING id",
        ('basic@kit.com', hashed_pw, True)
    ).fetchone()['id']
    
    # Agents
    agent_pro_id = db.execute("INSERT INTO agents (user_id, name, brokerage, email, phone) VALUES (%s, 'Pro Agent', 'Brok', 'p@k.com', '123') RETURNING id", (pro_id,)).fetchone()['id']
    agent_basic_id = db.execute("INSERT INTO agents (user_id, name, brokerage, email, phone) VALUES (%s, 'Basic Agent', 'Brok', 'b@k.com', '123') RETURNING id", (basic_id,)).fetchone()['id']
    
    # Properties
    prop_pro_id = db.execute("INSERT INTO properties (agent_id, address, beds, baths, slug, qr_code) VALUES (%s, '123 Pro St', '3', '2', 'pro-slug', 'pro-qr') RETURNING id", (agent_pro_id,)).fetchone()['id']
    prop_basic_id = db.execute("INSERT INTO properties (agent_id, address, beds, baths, slug, qr_code) VALUES (%s, '123 Basic St', '3', '2', 'basic-slug', 'basic-qr') RETURNING id", (agent_basic_id,)).fetchone()['id']
    
    db.commit()
    return {
        'pro_id': pro_id, 'basic_id': basic_id,
        'prop_pro_id': prop_pro_id, 'prop_basic_id': prop_basic_id,
        'pro_email': 'pro@kit.com', 'basic_email': 'basic@kit.com'
    }

# --- Tests ---

def test_pro_generates_kit_freely(client, db, kit_data):
    """Pro user can generate kit without paying."""
    client.post('/login', data={'email': kit_data['pro_email'], 'password': 'hash'})
    
    # Start generation
    # Must patch where it's used because of 'from ... import ...' style
    with patch('routes.listing_kits.generate_kit') as mock_gen:
        resp = client.post(f"/api/kits/{kit_data['prop_pro_id']}/start")
        assert resp.status_code == 200
        assert resp.json['status'] == 'generating'
        assert 'kit_id' in resp.json
        
        # Verify kit record created
        kit = db.execute("SELECT * FROM listing_kits WHERE id=%s", (resp.json['kit_id'],)).fetchone()
        assert kit
        assert kit['property_id'] == kit_data['prop_pro_id']
        
        mock_gen.assert_called_once()

def test_basic_requires_checkout(client, db, kit_data):
    """Non-pro user gets checkout link."""
    client.post('/login', data={'email': kit_data['basic_email'], 'password': 'hash'})
    
    with patch('stripe.checkout.Session.create') as mock_stripe:
        mock_stripe.return_value = MagicMock(id='sess_123', url='https://stripe.com/pay')
        
        # Configure price ID env var mock? 
        # config loaded already, but app.config used?
        # The route reads from config module. config module reads os.environ.
        # But config loaded at start time. 
        # Assuming app default 'price_listing_lock_id' is set if env missing or tests set it.
        # conftest.py sets env vars?
        
        resp = client.post(f"/api/kits/{kit_data['prop_basic_id']}/start")
        assert resp.status_code == 200
        assert resp.json['status'] == 'payment_required'
        assert resp.json['checkout_url'] == 'https://stripe.com/pay'
        
        # Verify Order Created
        order = db.execute(
            "SELECT * FROM orders WHERE user_id=%s AND property_id=%s AND order_type='listing_kit'", 
            (kit_data['basic_id'], kit_data['prop_basic_id'])
        ).fetchone()
        assert order
        assert order['status'] == 'pending_payment'

def test_webhook_fulfills_kit(client, db, kit_data):
    """Webhook payment triggers generation and unlocks property."""
    # 1. Create pending order
    order_id = db.execute(
        "INSERT INTO orders (user_id, property_id, status, order_type, amount_total_cents, currency) VALUES (%s, %s, 'pending_payment', 'listing_kit', 0, 'usd') RETURNING id",
        (kit_data['basic_id'], kit_data['prop_basic_id'])
    ).fetchone()['id']
    db.commit()
    
    # 2. Webhook payload
    payload = {
        'id': 'evt_test',
        'type': 'checkout.session.completed',
        'data': {
            'object': {
                'id': 'sess_123',
                'object': 'checkout.session',
                'mode': 'payment',
                'payment_status': 'paid',
                'amount_total': 1000,
                'currency': 'usd',
                'metadata': {
                    'order_id': order_id, # critical
                    'purpose': 'listing_kit'
                },
                'customer': 'cus_test'
            }
        }
    }
    
    with patch('stripe.Webhook.construct_event') as mock_construct:
        mock_construct.return_value = payload
        
        # Mock kit generation to avoid actual FS/PDF ops in this unit test
        # Webhook imports inside function, so patching services.* works
        with patch('services.listing_kits.generate_kit') as mock_gen:
            with patch('services.listing_kits.create_or_get_kit') as mock_create:
                mock_create.return_value = {'id': 999}
                
                resp = client.post('/stripe/webhook', headers={'Stripe-Signature': 'fake'}, json=payload)
                assert resp.status_code == 200
                
                # Verify Order Status
                order = db.execute("SELECT status FROM orders WHERE id=%s", (order_id,)).fetchone()
                assert order['status'] == 'paid'
                
                # Verify Property Unlock (expires_at -> NULL)
                prop = db.execute("SELECT expires_at FROM properties WHERE id=%s", (kit_data['prop_basic_id'],)).fetchone()
                assert prop['expires_at'] is None
                
                # Verify Kit Gen Triggered
                mock_create.assert_called_with(kit_data['basic_id'], kit_data['prop_basic_id'])
                mock_gen.assert_called_with(999)

def test_download_access_control(client, db, kit_data):
    """Test ownership check on download."""
    client.post('/login', data={'email': kit_data['basic_email'], 'password': 'hash'})
    
    # Setup: Kit exists for PRO user
    db.execute(
        "INSERT INTO listing_kits (user_id, property_id, status, kit_zip_path) VALUES (%s, %s, 'ready', 'path/to/zip')",
        (kit_data['pro_id'], kit_data['prop_pro_id'])
    )
    kit_id = db.execute("SELECT id FROM listing_kits WHERE property_id=%s", (kit_data['prop_pro_id'],)).fetchone()['id']
    db.commit()
    
    # Basic user tries to download Pro's kit
    resp = client.get(f"/api/kits/{kit_id}/download")
    assert resp.status_code == 404 # Not found or Unauthorized (code uses 404 for security)

def test_paid_kit_allows_start_freely(client, db, kit_data):
    """If property is paid (even by basic user), start generation freely."""
    client.post('/login', data={'email': kit_data['basic_email'], 'password': 'hash'})
    
    # Mark property as paid via listing_kit
    # How? gating service checks orders.
    db.execute(
        "INSERT INTO orders (user_id, property_id, status, order_type) VALUES (%s, %s, 'paid', 'listing_kit')",
        (kit_data['basic_id'], kit_data['prop_basic_id'])
    )
    db.commit()
    
    with patch('routes.listing_kits.generate_kit') as mock_gen:
        resp = client.post(f"/api/kits/{kit_data['prop_basic_id']}/start")
        # Should NOT ask for payment
        assert resp.status_code == 200
        assert resp.json['status'] == 'generating'
        mock_gen.assert_called_once()


def test_listing_unlock_does_not_grant_kit_generation(client, db, kit_data):
    """Regression test: Listing unlock purchase should NOT allow kit generation."""
    client.post('/login', data={'email': kit_data['basic_email'], 'password': 'hash'})
    
    # 1. Insert PAID order for 'listing_unlock'
    db.execute(
        "INSERT INTO orders (user_id, property_id, status, order_type) VALUES (%s, %s, 'paid', 'listing_unlock')",
        (kit_data['basic_id'], kit_data['prop_basic_id'])
    )
    db.commit()
    
    # 2. Attempt to start kit generation
    with patch('stripe.checkout.Session.create') as mock_stripe:
        mock_stripe.return_value = MagicMock(id='sess_unlock_fail', url='https://stripe.com/pay_kit')
        
        resp = client.post(f"/api/kits/{kit_data['prop_basic_id']}/start")
        
        # Should be redirected to payment (200 with status='payment_required'), NOT 200 generating
        assert resp.status_code == 200
        assert resp.json['status'] == 'payment_required'
        assert resp.json['checkout_url'] == 'https://stripe.com/pay_kit'
    
    # 3. Now verify PAID 'listing_kit' DOES work
    db.execute(
        "UPDATE orders SET order_type='listing_kit' WHERE user_id=%s AND property_id=%s",
        (kit_data['basic_id'], kit_data['prop_basic_id'])
    )
    db.commit()
    
    with patch('routes.listing_kits.generate_kit') as mock_gen:
        resp = client.post(f"/api/kits/{kit_data['prop_basic_id']}/start")
        assert resp.status_code == 200
        assert resp.json['status'] == 'generating'
