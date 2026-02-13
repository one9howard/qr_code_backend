import pytest
import sys
import os
# Force project root into path for this test execution
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from unittest.mock import patch, MagicMock
from services.orders import create_sign_order
from models import Order, User, Property

@pytest.fixture
def db_setup(db_session):
    import uuid
    uid = str(uuid.uuid4())[:8]
    email = f'test-{uid}@ord.er'
    address = f'123 Order St {uid}'
    
    # Setup basic user/agent/property
    db_session.execute("INSERT INTO users (email, password_hash, subscription_status) VALUES (%s, 'hash', 'free')", (email,))
    user_id = db_session.execute("SELECT id FROM users WHERE email=%s", (email,)).fetchone()[0]
    
    db_session.execute("INSERT INTO agents (user_id, name, brokerage, email) VALUES (%s, 'Agent', 'Broke', %s)", (user_id, f'a-{uid}@b.com'))
    agent_id = db_session.execute("SELECT id FROM agents WHERE user_id=%s", (user_id,)).fetchone()[0]
    
    db_session.execute("INSERT INTO properties (agent_id, address, beds, baths) VALUES (%s, %s, '3', '2')", (agent_id, address))
    prop_id = db_session.execute("SELECT id FROM properties WHERE address=%s", (address,)).fetchone()[0]
    
    db_session.commit()
    return user_id, prop_id

def test_create_order_requires_login(db_session):
    """Refactor Check: Anonymous user cannot start new order."""
    res = create_sign_order(None, {
        'property_id': 1
    })
    assert res['success'] is False
    assert "Login required" in res['error']


class SimpleUser:
    def __init__(self, id, email, is_authenticated=True, is_admin=False):
        self.id = id
        self.email = email
        self.is_authenticated = is_authenticated
        self.is_admin = is_admin

def test_create_order_success(db_session, db_setup):
    """Refactor Check: Authenticated user can start order."""
    user_id, prop_id = db_setup
    
    # Simple User object
    # Fetch email from DB to match unique constraint
    email = db_session.execute("SELECT email FROM users WHERE id=%s", (user_id,)).fetchone()[0]
    user = SimpleUser(id=user_id, email=email)
    
    with patch('stripe.checkout.Session.create') as mock_stripe, \
         patch('services.orders.get_price_id', return_value='price_fake_123'):
        mock_stripe.return_value = MagicMock(url='http://stripe.url')
        
        # Test
        res = create_sign_order(user, {
            'property_id': prop_id,
            'size': '18x24'
        })
        
        assert res['success'] is True, f"Order creation failed: {res}"
        assert res['checkoutUrl'] == 'http://stripe.url'
        
        # Verify DB
        order_row = db_session.execute("SELECT * FROM orders WHERE user_id=%s", (user_id,)).fetchone()
        assert order_row is not None
        assert order_row['order_type'] == 'sign'
        assert order_row['status'] == 'pending_payment'
        assert order_row['sign_size'] == '18x24'

def test_update_existing_order(db_session, db_setup):
    """Refactor Check: Updating existing order (e.g. guest flow)."""
    user_id, prop_id = db_setup
    
    # Create initial order manually
    db_session.execute("INSERT INTO orders (user_id, property_id, status, order_type) VALUES (%s, %s, 'pending_payment', 'sign')", (user_id, prop_id))
    order_id = db_session.execute("SELECT id FROM orders WHERE user_id=%s", (user_id,)).fetchone()[0]
    db_session.commit()
    
    user = SimpleUser(id=user_id, email='test@ord.er')

    with patch('stripe.checkout.Session.create') as mock_stripe, \
         patch('services.orders.get_order_for_request') as mock_get_order, \
         patch('services.orders.get_price_id', return_value='price_fake_456'):
        
        mock_stripe.return_value = MagicMock(url='http://stripe.update')
        
        # Mock authorized order retrieval
        mock_order = MagicMock()
        mock_order.id = order_id
        mock_order.property_id = prop_id
        mock_order.sign_size = '18x24'
        mock_order.layout_id = None
        mock_order.guest_email = None
        mock_get_order.return_value = mock_order

        # Call with existing order_id and NEW color
        res = create_sign_order(user, {
            'order_id': order_id,
            'color': '#FF0000'
        })
        
        assert res['success'] is True, f"Update failed: {res}"
        assert res['checkoutUrl'] == 'http://stripe.update'
        
        # Verify Update
        order_row = db_session.execute("SELECT * FROM orders WHERE id=%s", (order_id,)).fetchone()
        assert order_row['sign_color'] == '#FF0000', f"Color not updated: {order_row['sign_color']}"

def test_unauthorized_property(db_session, db_setup):
    """Refactor Check: User cannot order for another agent's property."""
    user_id, prop_id = db_setup
    
    # Create another user
    db_session.execute("INSERT INTO users (email, password_hash, subscription_status) VALUES ('hacker@t.com', 'x', 'free')")
    hacker_id = db_session.execute("SELECT id FROM users WHERE email='hacker@t.com'").fetchone()[0]
    
    hacker = SimpleUser(id=hacker_id, email='hacker@t.com')
    
    res = create_sign_order(hacker, {
        'property_id': prop_id
    })
    
    assert res['success'] is False, f"Unauthorized check failed, got success: {res}"
    assert "Unauthorized property access" in res['error'], f"Wrong error: {res['error']}"
