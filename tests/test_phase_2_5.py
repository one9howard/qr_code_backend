
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
from routes.webhook import handle_payment_checkout
from services.smart_signs import SmartSignsService
from database import get_db


def _force_login(client, user_id):
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user_id)
        sess['_fresh'] = True

@pytest.fixture
def mock_stripe_session():
    return {
        'id': 'cs_test_123',
        'payment_status': 'paid',
        'metadata': {
            'purpose': 'smart_sign',
            'sign_asset_id': '1', # Will be updated in test
            'user_id': '1',
            'order_id': '1'
        },
        'payment_intent': 'pi_123',
        'amount_total': 5000,
        'currency': 'usd'
    }

class AuthActions:
    def __init__(self, client, db):
        self._client = client
        self._db = db

    def login_pro(self, email="pro@test.com"):
        from werkzeug.security import generate_password_hash
        pw_hash = generate_password_hash("password")
        
        user = self._db.execute("SELECT * FROM users WHERE email=%s", (email,)).fetchone()
        
        if not user:
            user_id = self._db.execute(
                "INSERT INTO users (email, password_hash, subscription_status, is_verified) VALUES (%s, %s, 'active', true) RETURNING id",
                (email, pw_hash)
            ).fetchone()['id']
            # Create Agent key for property creation
            self._db.execute("INSERT INTO agents (user_id, name, brokerage, email) VALUES (%s, 'Pro', 'Brokerage', %s)", (user_id, email))
            self._db.commit()
        else:
            user_id = user['id']

        # Return Mock User object
        class User: pass
        u = User()
        u.id = user_id
        u.email = email
        return u

@pytest.fixture
def auth(client, db):
    return AuthActions(client, db)

def test_webhook_idempotency_activation(client, app, db, auth, mock_stripe_session):
    """Verify that processing the same webhook twice triggers activation only once."""
    user = auth.login_pro()
    
    # 1. Create Unactivated Asset (via Service directly)
    # db fixture ensures app context is active
    
    # We need a property for creation now? No, optional in service if we pass None, 
    # but route enforces it. Service allows None (default) but logic inside might require checking.
    # Service create_asset signature: create_asset(user_id, label=None, active_property_id=None)
    # We can pass active_property_id=None for this test to simulate "just created".
    
    # 1. Create Property & Asset
    # Create valid property first (Option B requires it)
    # MUST provide required fields (beds, baths)
    prop_id = db.execute("INSERT INTO properties (agent_id, address, beds, baths) VALUES ((SELECT id FROM agents WHERE user_id=%s), '123 Test St', '3', '2') RETURNING id", (user.id,)).fetchone()['id']
    
    asset_row = SmartSignsService.create_asset_for_purchase(user.id, property_id=prop_id, label="Test Asset")
    asset = dict(asset_row)
    asset_id = asset['id']
    
    # 2. Create Order (with property_id NOT NULL)
    row = db.execute("""
        INSERT INTO orders (user_id, property_id, sign_asset_id, status, order_type, created_at)
        VALUES (%s, %s, %s, 'pending_payment', 'smart_sign', CURRENT_TIMESTAMP)
        RETURNING id
    """, (user.id, prop_id, asset_id)).fetchone()
    order_id = row['id']
    db.commit()

    # Update mock session
    mock_stripe_session['metadata']['sign_asset_id'] = str(asset_id)
    mock_stripe_session['metadata']['order_id'] = str(order_id)
    mock_stripe_session['metadata']['property_id'] = str(prop_id)
    mock_stripe_session['metadata']['user_id'] = str(user.id)

    # 3. Simulate Webhook calls
    with patch('services.async_jobs.enqueue', return_value='job_test') as mock_enqueue:
        handle_payment_checkout(db, mock_stripe_session)

        # Check Activation
        updated_asset = db.execute("SELECT activated_at FROM sign_assets WHERE id=%s", (asset_id,)).fetchone()
        assert updated_asset['activated_at'] is not None
        first_activation = updated_asset['activated_at']

        # Check async enqueue happened
        assert mock_enqueue.call_count == 1

        # Check Property Unlocked
        prop = db.execute("SELECT expires_at FROM properties WHERE id=%s", (prop_id,)).fetchone()
        assert prop['expires_at'] is None

        # 4. Simulate Webhook 2nd Call (without print_jobs row, enqueue happens again)
        handle_payment_checkout(db, mock_stripe_session)

        updated_asset_2 = db.execute("SELECT activated_at FROM sign_assets WHERE id=%s", (asset_id,)).fetchone()
        assert updated_asset_2['activated_at'] == first_activation  # idempotent activation timestamp
        assert mock_enqueue.call_count == 2

        # 5. Insert print_jobs row and verify future call is skipped
        db.execute("""
            INSERT INTO print_jobs (idempotency_key, job_id, order_id, status, attempts, updated_at) 
            VALUES (%s, %s, %s, 'queued', 0, CURRENT_TIMESTAMP)
        """, (f"chk_{order_id}", f"test_job_{order_id}", order_id))
        db.commit()

        handle_payment_checkout(db, mock_stripe_session)
        assert mock_enqueue.call_count == 2

def test_assignment_rules(client, app, db, auth):
    """Verify Assignment rules: Pro + Activated + Not Frozen."""
    user = auth.login_pro() # Active Pro
    # db fixture ensures app context
    
    # 1. Create Property FIRST (Required for creation)
    prop_id = db.execute("INSERT INTO properties (agent_id, address, beds, baths) VALUES ((SELECT id FROM agents WHERE user_id=%s), '123 Test St', '1', '1') RETURNING id", (user.id,)).fetchone()['id']
    db.commit()

    # 2. Create Unactivated Asset
    asset_row = SmartSignsService.create_asset_for_purchase(user.id, property_id=prop_id, label="Rule Test")
    asset_id = asset_row['id']
    db.commit()
    
    # 2. Try to Assign (Should Fail - Not Activated)
    with pytest.raises(ValueError, match="must be activated"):
        SmartSignsService.assign_asset(asset_id, prop_id, user.id)
        
    # 3. Activate Manually
    activation_order_id = db.execute(
        """
        INSERT INTO orders (user_id, property_id, status, order_type, created_at)
        VALUES (%s, %s, 'paid', 'smart_sign', CURRENT_TIMESTAMP)
        RETURNING id
        """,
        (user.id, prop_id)
    ).fetchone()['id']
    db.execute(
        "UPDATE sign_assets SET activated_at = CURRENT_TIMESTAMP, activation_order_id = %s WHERE id=%s",
        (activation_order_id, asset_id),
    )
    db.commit()
    
    # 4. Assign (Should Success)
    SmartSignsService.assign_asset(asset_id, prop_id, user.id)
    
    # 5. Freeze
    db.execute("UPDATE sign_assets SET is_frozen = true WHERE id=%s", (asset_id,))
    db.commit()
    
    # 6. Try to Assign (Should Fail - Frozen)
    with pytest.raises(ValueError, match="is frozen"):
        SmartSignsService.assign_asset(asset_id, None, user.id) # Unassign attempt

def test_smart_sign_checkout_endpoint_disabled(client, app, db, auth):
    'Legacy /orders/smart-sign/checkout is intentionally disabled; canonical flow lives under /smart-signs.'
    user = auth.login_pro()
    _force_login(client, user.id)

    resp = client.post('/orders/smart-sign/checkout', data={'asset_id': 1, 'property_id': 1})
    assert resp.status_code == 404
