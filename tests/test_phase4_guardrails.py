"""
Phase 4 Guardrails Tests

Tests for:
- Free tier property creation limits
- SmartSign reassignment rules
- Proper reason codes in responses
"""
import pytest
from unittest.mock import patch, MagicMock
from werkzeug.security import generate_password_hash


# --- Fixtures ---

@pytest.fixture
def phase4_data(client, db):
    """Setup data for Phase 4 guardrail tests."""
    hashed_pw = generate_password_hash('testpass')
    
    # Pro user
    pro_id = db.execute(
        "INSERT INTO users (email, password_hash, is_verified, subscription_status) VALUES (%s, %s, %s, 'active') RETURNING id",
        ('phase4pro@test.com', hashed_pw, True)
    ).fetchone()['id']
    
    # Free user
    free_id = db.execute(
        "INSERT INTO users (email, password_hash, is_verified, subscription_status) VALUES (%s, %s, %s, 'inactive') RETURNING id",
        ('phase4free@test.com', hashed_pw, True)
    ).fetchone()['id']
    
    # Agents for both users
    pro_agent_id = db.execute(
        "INSERT INTO agents (user_id, name, brokerage, email, phone) VALUES (%s, 'Pro Agent', 'Test Brokerage', 'pro@test.com', '123-456-7890') RETURNING id",
        (pro_id,)
    ).fetchone()['id']
    
    free_agent_id = db.execute(
        "INSERT INTO agents (user_id, name, brokerage, email, phone) VALUES (%s, 'Free Agent', 'Test Brokerage', 'free@test.com', '123-456-7890') RETURNING id",
        (free_id,)
    ).fetchone()['id']
    
    db.commit()
    
    return {
        'pro_id': pro_id,
        'free_id': free_id,
        'pro_agent_id': pro_agent_id,
        'free_agent_id': free_agent_id,
        'pro_email': 'phase4pro@test.com',
        'free_email': 'phase4free@test.com',
        'password': 'testpass'
    }


# --- A1: Free Plan Max Active Listings Tests ---

def test_free_user_cannot_create_second_property(client, db, phase4_data):
    """Free user with 1 property cannot create a second one."""
    # Login as free user
    client.post('/login', data={'email': phase4_data['free_email'], 'password': phase4_data['password']})
    
    # Create first property for free user
    db.execute(
        "INSERT INTO properties (agent_id, address, beds, baths, slug, qr_code) VALUES (%s, 'First Property', '3', '2', 'first-prop', 'first-qr')",
        (phase4_data['free_agent_id'],)
    )
    db.commit()
    
    # Attempt to create second property via submit route
    resp = client.post('/submit', data={
        'address': 'Second Property',
        'beds': '4',
        'baths': '2',
        'agent_name': 'Free Agent',
        'brokerage': 'Test Brokerage',
        'email': 'free@test.com',
        'phone': '123-456-7890'
    })
    
    # Should return 402 (Payment Required)
    assert resp.status_code == 402
    assert b'Upgrade to Pro' in resp.data or b'unlimited listings' in resp.data


def test_pro_user_can_create_multiple_properties(client, db, phase4_data):
    """Pro user can create multiple properties without limits."""
    # Login as pro user
    client.post('/login', data={'email': phase4_data['pro_email'], 'password': phase4_data['password']})
    
    # Create first property for pro user
    db.execute(
        "INSERT INTO properties (agent_id, address, beds, baths, slug, qr_code) VALUES (%s, 'Pro First', '3', '2', 'pro-first', 'prof-qr')",
        (phase4_data['pro_agent_id'],)
    )
    db.commit()
    
    # Attempt to create second property
    resp = client.post('/submit', data={
        'address': 'Pro Second Property',
        'beds': '5',
        'baths': '3',
        'agent_name': 'Pro Agent',
        'brokerage': 'Test Brokerage',
        'email': 'pro@test.com',
        'phone': '123-456-7890'
    })
    
    # Should succeed (200 or redirect to asset page)
    assert resp.status_code in (200, 302, 303)
    
    # Verify property was created
    props = db.execute(
        "SELECT COUNT(*) as cnt FROM properties WHERE agent_id = %s",
        (phase4_data['pro_agent_id'],)
    ).fetchone()
    assert props['cnt'] >= 2


# --- A2: SmartSign Reassignment Tests ---

def _create_test_asset(db, user_id, activated=True, frozen=False, property_id=None):
    """Helper to create a test sign asset."""
    import secrets
    code = secrets.token_urlsafe(9)[:12]
    
    db.execute(
        """INSERT INTO sign_assets (user_id, code, active_property_id, is_frozen, activated_at) 
           VALUES (%s, %s, %s, %s, %s) RETURNING id""",
        (user_id, code, property_id, frozen, 'now()' if activated else None)
    )
    asset = db.execute("SELECT * FROM sign_assets WHERE code = %s", (code,)).fetchone()
    db.commit()
    return asset


def test_reassign_requires_pro(app, client, db, phase4_data):
    """SmartSign reassignment requires Pro subscription."""
    # Create an activated asset for free user
    asset = _create_test_asset(db, phase4_data['free_id'], activated=True, frozen=False)
    
    # Create a property to assign to
    db.execute(
        "INSERT INTO properties (agent_id, address, beds, baths, slug, qr_code) VALUES (%s, 'Target Prop', '2', '1', 'target-prop', 'target-qr')",
        (phase4_data['free_agent_id'],)
    )
    prop = db.execute("SELECT id FROM properties WHERE slug = 'target-prop'").fetchone()
    db.commit()
    
    # Login as free user
    client.post('/login', data={'email': phase4_data['free_email'], 'password': phase4_data['password']})
    
    # Attempt to assign
    resp = client.post(f'/dashboard/smart-signs/{asset["id"]}/assign', data={'property_id': str(prop['id'])})
    
    # Should redirect with error flash (check for upgrade message)
    assert resp.status_code in (302, 303)
    
    # Follow redirect and check for flash message
    follow_resp = client.get('/dashboard', follow_redirects=True)
    assert b'Upgrade' in follow_resp.data or b'upgrade' in follow_resp.data


def test_reassign_requires_activated(app, client, db, phase4_data):
    """SmartSign reassignment requires activated asset."""
    # Create an UNACTIVATED asset for pro user
    asset = _create_test_asset(db, phase4_data['pro_id'], activated=False, frozen=False)
    
    # Create a property to assign to
    db.execute(
        "INSERT INTO properties (agent_id, address, beds, baths, slug, qr_code) VALUES (%s, 'Target2', '2', '1', 'target2', 'target2-qr')",
        (phase4_data['pro_agent_id'],)
    )
    prop = db.execute("SELECT id FROM properties WHERE slug = 'target2'").fetchone()
    db.commit()
    
    # Login as pro user
    client.post('/login', data={'email': phase4_data['pro_email'], 'password': phase4_data['password']})
    
    # Attempt to assign
    resp = client.post(f'/dashboard/smart-signs/{asset["id"]}/assign', data={'property_id': str(prop['id'])})
    
    # Should redirect with error
    assert resp.status_code in (302, 303)
    
    # Follow redirect and check for activation message
    follow_resp = client.get('/dashboard', follow_redirects=True)
    assert b'activated' in follow_resp.data.lower()


def test_reassign_blocked_when_frozen(app, client, db, phase4_data):
    """SmartSign reassignment blocked when asset is frozen."""
    # Create a FROZEN asset for pro user
    asset = _create_test_asset(db, phase4_data['pro_id'], activated=True, frozen=True)
    
    # Create a property to assign to
    db.execute(
        "INSERT INTO properties (agent_id, address, beds, baths, slug, qr_code) VALUES (%s, 'Target3', '2', '1', 'target3', 'target3-qr')",
        (phase4_data['pro_agent_id'],)
    )
    prop = db.execute("SELECT id FROM properties WHERE slug = 'target3'").fetchone()
    db.commit()
    
    # Login as pro user
    client.post('/login', data={'email': phase4_data['pro_email'], 'password': phase4_data['password']})
    
    # Attempt to assign
    resp = client.post(f'/dashboard/smart-signs/{asset["id"]}/assign', data={'property_id': str(prop['id'])})
    
    # Should redirect with error
    assert resp.status_code in (302, 303)
    
    # Follow redirect and check for frozen message
    follow_resp = client.get('/dashboard', follow_redirects=True)
    assert b'frozen' in follow_resp.data.lower()


# --- A3: Listing Kit Generation Gate (reason code check) ---

def test_listing_kit_returns_reason_code(client, db, phase4_data):
    """Non-Pro user gets payment_required response with reason code."""
    # Login as free user
    client.post('/login', data={'email': phase4_data['free_email'], 'password': phase4_data['password']})
    
    # Create a property for free user
    db.execute(
        "INSERT INTO properties (agent_id, address, beds, baths, slug, qr_code) VALUES (%s, 'Kit Test', '2', '1', 'kit-test', 'kit-qr')",
        (phase4_data['free_agent_id'],)
    )
    prop = db.execute("SELECT id FROM properties WHERE slug = 'kit-test'").fetchone()
    db.commit()
    
    # Attempt to start kit generation
    with patch('stripe.checkout.Session.create') as mock_stripe:
        mock_stripe.return_value = MagicMock(id='sess_test', url='https://stripe.com/checkout')
        
        resp = client.post(f'/api/kits/{prop["id"]}/start')
        
        # Should return 200 with payment_required status or 402 if pricing not configured
        if resp.status_code == 402:
            # Config not set - check for reason code
            assert resp.json.get('reason') == 'kit_not_purchased'
        else:
            assert resp.status_code == 200
            assert resp.json.get('status') == 'payment_required'
            assert resp.json.get('reason') == 'kit_not_purchased'
