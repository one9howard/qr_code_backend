import pytest
from flask import url_for
from database import get_db

class TestPropertyCreationFlow:
    
    @pytest.fixture
    def test_user(self, app):
        with app.app_context():
            db = get_db()
            ur = db.execute(
                "INSERT INTO users (email, password_hash, is_verified, subscription_status) VALUES ('prop_flow@test.com', 'x', true, 'active') RETURNING id"
            ).fetchone()
            # Create agent to simplify flow
            db.execute("INSERT INTO agents (user_id, name, email, brokerage, phone) VALUES (%s, 'Test Agent', 'prop_flow@test.com', 'Test Brokerage', '555-0199')", (ur['id'],))
            db.commit()
            return ur

    def test_get_submit_page_property_only_mode(self, client, app, test_user):
        """
        Verify that accessing submit page with mode='property_only'
        renders the Property Creation UI (header, hidden input) 
        and hides the Sign Configuration section.
        """
        # Login
        with client.session_transaction() as sess:
            sess['_user_id'] = str(test_user['id'])
            sess['_fresh'] = True
            
        # Act
        resp = client.get('/submit?mode=property_only')
        html = resp.data.decode('utf-8')
        
        # Assertions
        assert 'Create Property (Free)' in html
        assert '<input type="hidden" name="mode" value="property_only">' in html
        assert 'Create Property' in html

    def test_create_property_only_does_not_create_order(self, client, app, test_user):
        """
        Verify that POSTing to submit with mode='property_only'
        creates a property but DOES NOT create an order,
        and redirects to dashboard.
        """
        # Login
        with client.session_transaction() as sess:
            sess['_user_id'] = str(test_user['id'])
            sess['_fresh'] = True
            
        # Act
        data = {
            'mode': 'property_only',
            'address': '999 Property Only St',
            'beds': '4',
            'baths': '3',
            'agent_name': 'Test Agent',
            'brokerage': 'Test Brokerage',
            'email': 'prop_flow@test.com',
            'phone': '555-0199',
            'sign_size': '18x24', # Form might still send defaults
            'sign_color': '#000000',
            'layout_id': 'smart_v1_minimal'
        }
        
        # Follow redirects to check final landing page
        resp = client.post('/submit', data=data, follow_redirects=True)
        html = resp.data.decode('utf-8')
        
        # Assertions
        
        # 1. Redirected to Dashboard
        # The URL should match dashboard index. 
        # Note: follow_redirects=True makes resp.request.path the final path
        assert '/dashboard' in resp.request.path
        
        # 2. Flash message
        # "Property created successfully. Now assign your SmartSign."
        assert 'Property created successfully' in html
        
        # 3. DB State
        with app.app_context():
            db = get_db()
            
            # Property MUST exist
            prop = db.execute("SELECT * FROM properties WHERE address='999 Property Only St'").fetchone()
            assert prop is not None
            
            # Order MUST NOT exist for this user
            order = db.execute("SELECT * FROM orders WHERE user_id=%s", (test_user['id'],)).fetchone()
            assert order is None

    def test_standard_flow_creates_order(self, client, app):
        """
        Regression Test: Ensure standard flow (no mode) STILL creates an order.
        """
        # Create separate user
        with app.app_context():
            db = get_db()
            ur = db.execute(
                "INSERT INTO users (email, password_hash, is_verified, subscription_status) VALUES ('std_flow@test.com', 'x', true, 'active') RETURNING id"
            ).fetchone()
            db.commit()
            
        with client.session_transaction() as sess:
            sess['_user_id'] = str(ur['id'])
            sess['_fresh'] = True
            
        data = {
            'address': '123 Standard St',
            'beds': '2',
            'baths': '2',
            'agent_name': 'Std Agent',
            'brokerage': 'Std Broker',
            'email': 'std_flow@test.com',
            'phone': '555-0000'
            # No mode
        }
        
        resp = client.post('/submit', data=data, follow_redirects=True)
        
        # Standard flow redirects to Assets page usually, or Checkout if pending payment
        # Since logic returns `render_template("assets.html", ...)` for POST success (line 352 in agent.py)
        # It renders 'assets.html' with Order ID.
        
        assert 'assets.html' in resp.data.decode('utf-8') or 'Pending Payment' in resp.data.decode('utf-8')
        
        with app.app_context():
            db = get_db()
            order = db.execute("SELECT * FROM orders WHERE user_id=%s", (ur['id'],)).fetchone()
            assert order is not None
            assert order['status'] == 'pending_payment'
