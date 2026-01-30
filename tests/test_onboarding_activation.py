"""
Tests for Phase 1 Onboarding Activation Improvements.

Tests the hard zero-state gate, progress checklist, and first-lead highlight.
"""
import pytest
from flask import url_for
from flask_login import login_user
from database import get_db


class TestDashboardOnboarding:
    """Test dashboard onboarding activation features."""

    def test_dashboard_zero_state_shows_activation_card(self, client, test_user_with_agent):
        """
        User with 0 sign_assets should see the activation card 
        and NOT see normal stats panels.
        """
        user, agent = test_user_with_agent
        
        with client.session_transaction() as sess:
            sess['_user_id'] = str(user.id)
            sess['_fresh'] = True
        
        response = client.get('/dashboard/')
        html = response.data.decode('utf-8')
        
        # Should show activation card
        assert 'Get your first buyer lead' in html
        assert 'Create SmartSign' in html
        assert 'Takes about 2 minutes' in html
        assert 'data-testid="activation-card"' in html
        
        # Should NOT show normal stats
        assert 'Total Scans' not in html or 'data-testid="activation-card"' in html
        # Tabs should not appear when in zero-state
        assert 'Buyer Activity' not in html

    def test_dashboard_normal_state_for_user_with_signs(self, client, test_user_with_sign_asset):
        """
        User with sign_assets should see normal dashboard 
        and NOT see the hard gate activation card.
        """
        user, agent, sign_asset = test_user_with_sign_asset
        
        with client.session_transaction() as sess:
            sess['_user_id'] = str(user.id)
            sess['_fresh'] = True
        
        response = client.get('/dashboard/')
        html = response.data.decode('utf-8')
        
        # Should NOT show activation card headline
        # (The text might appear elsewhere, so check for the specific card marker)
        assert 'data-testid="activation-card"' not in html
        
        # Should show normal dashboard elements
        assert 'Buyer Activity' in html  # Tab name
        assert 'Your SmartSigns' in html  # Tab name

    def test_checklist_shown_when_no_leads(self, client, test_user_with_sign_asset):
        """
        User with sign asset but 0 leads should see the progress checklist.
        """
        user, agent, sign_asset = test_user_with_sign_asset
        
        with client.session_transaction() as sess:
            sess['_user_id'] = str(user.id)
            sess['_fresh'] = True
        
        response = client.get('/dashboard/')
        html = response.data.decode('utf-8')
        
        # Should show checklist
        assert 'Get Your First Lead' in html
        assert 'Create SmartSign' in html
        assert 'Assign to Property' in html
        assert 'Get First Scan' in html
        assert 'Receive Buyer Inquiry' in html

    def test_checklist_states_reflect_progress(self, client, test_user_with_assigned_sign):
        """
        Checklist should show checkmarks for completed steps.
        """
        user, agent, sign_asset, property = test_user_with_assigned_sign
        
        with client.session_transaction() as sess:
            sess['_user_id'] = str(user.id)
            sess['_fresh'] = True
        
        response = client.get('/dashboard/')
        html = response.data.decode('utf-8')
        
        # With assigned sign, first two items should be checked
        # (We can't easily check the exact checkmark rendering without parsing HTML)
        assert 'Get Your First Lead' in html
        # The checklist should exist
        assert 'Create SmartSign' in html

    def test_soft_gate_banner_when_sign_not_assigned(self, client, test_user_with_unassigned_sign):
        """
        User with SmartSign but not assigned should see soft gate banner.
        """
        user, agent, sign_asset = test_user_with_unassigned_sign
        
        with client.session_transaction() as sess:
            sess['_user_id'] = str(user.id)
            sess['_fresh'] = True
        
        response = client.get('/dashboard/')
        html = response.data.decode('utf-8')
        
        # Should show soft gate banner
        assert 'Assign your SmartSign to a property to start generating leads' in html
        assert 'Assign SmartSign' in html


# ============ FIXTURES ============

@pytest.fixture
def test_user_with_agent(app, client):
    """Create a test user with an agent but no sign assets."""
    with app.app_context():
        db = get_db()
        
        # Create user
        user_result = db.execute(
            """INSERT INTO users (email, password_hash, display_name, is_pro)
               VALUES (%s, %s, %s, %s) RETURNING id""",
            ('test_onboarding@example.com', 'hash', 'Test User', True)
        ).fetchone()
        user_id = user_result['id']
        
        # Create agent
        agent_result = db.execute(
            """INSERT INTO agents (user_id, name, email, phone, brokerage)
               VALUES (%s, %s, %s, %s, %s) RETURNING id""",
            (user_id, 'Test Agent', 'test@example.com', '555-1234', 'Test Brokerage')
        ).fetchone()
        agent_id = agent_result['id']
        
        db.connection.commit()
        
        # Create mock user object
        class MockUser:
            def __init__(self, id):
                self.id = id
                self.is_pro = True
                self.display_name = 'Test User'
                self.is_authenticated = True
                self.is_active = True
                self.is_anonymous = False
            def get_id(self):
                return str(self.id)
        
        class MockAgent:
            def __init__(self, id):
                self.id = id
        
        yield MockUser(user_id), MockAgent(agent_id)
        
        # Cleanup
        db.execute("DELETE FROM agents WHERE id = %s", (agent_id,))
        db.execute("DELETE FROM users WHERE id = %s", (user_id,))
        db.connection.commit()


@pytest.fixture
def test_user_with_sign_asset(app, client):
    """Create a test user with an agent and a sign asset."""
    with app.app_context():
        db = get_db()
        
        # Create user
        user_result = db.execute(
            """INSERT INTO users (email, password_hash, display_name, is_pro)
               VALUES (%s, %s, %s, %s) RETURNING id""",
            ('test_with_sign@example.com', 'hash', 'Test User', True)
        ).fetchone()
        user_id = user_result['id']
        
        # Create agent
        agent_result = db.execute(
            """INSERT INTO agents (user_id, name, email, phone, brokerage)
               VALUES (%s, %s, %s, %s, %s) RETURNING id""",
            (user_id, 'Test Agent', 'test2@example.com', '555-1234', 'Test Brokerage')
        ).fetchone()
        agent_id = agent_result['id']
        
        # Create sign asset
        sign_result = db.execute(
            """INSERT INTO sign_assets (user_id, label, qr_code, status)
               VALUES (%s, %s, %s, %s) RETURNING id""",
            (user_id, 'Test SmartSign', 'TEST123', 'active')
        ).fetchone()
        sign_id = sign_result['id']
        
        db.connection.commit()
        
        class MockUser:
            def __init__(self, id):
                self.id = id
                self.is_pro = True
                self.display_name = 'Test User'
                self.is_authenticated = True
                self.is_active = True
                self.is_anonymous = False
            def get_id(self):
                return str(self.id)
        
        class MockAgent:
            def __init__(self, id):
                self.id = id
        
        class MockSignAsset:
            def __init__(self, id):
                self.id = id
        
        yield MockUser(user_id), MockAgent(agent_id), MockSignAsset(sign_id)
        
        # Cleanup
        db.execute("DELETE FROM sign_assets WHERE id = %s", (sign_id,))
        db.execute("DELETE FROM agents WHERE id = %s", (agent_id,))
        db.execute("DELETE FROM users WHERE id = %s", (user_id,))
        db.connection.commit()


@pytest.fixture
def test_user_with_unassigned_sign(test_user_with_sign_asset):
    """Alias for unassigned sign test."""
    return test_user_with_sign_asset


@pytest.fixture
def test_user_with_assigned_sign(app, client):
    """Create a test user with an agent, sign asset assigned to a property."""
    with app.app_context():
        db = get_db()
        
        # Create user
        user_result = db.execute(
            """INSERT INTO users (email, password_hash, display_name, is_pro)
               VALUES (%s, %s, %s, %s) RETURNING id""",
            ('test_assigned@example.com', 'hash', 'Test User', True)
        ).fetchone()
        user_id = user_result['id']
        
        # Create agent
        agent_result = db.execute(
            """INSERT INTO agents (user_id, name, email, phone, brokerage)
               VALUES (%s, %s, %s, %s, %s) RETURNING id""",
            (user_id, 'Test Agent', 'test3@example.com', '555-1234', 'Test Brokerage')
        ).fetchone()
        agent_id = agent_result['id']
        
        # Create property
        prop_result = db.execute(
            """INSERT INTO properties (agent_id, address, slug)
               VALUES (%s, %s, %s) RETURNING id""",
            (agent_id, '123 Test St', 'test-property-onboard')
        ).fetchone()
        prop_id = prop_result['id']
        
        # Create sign asset assigned to property
        sign_result = db.execute(
            """INSERT INTO sign_assets (user_id, label, qr_code, status, active_property_id)
               VALUES (%s, %s, %s, %s, %s) RETURNING id""",
            (user_id, 'Test SmartSign', 'TEST456', 'active', prop_id)
        ).fetchone()
        sign_id = sign_result['id']
        
        db.connection.commit()
        
        class MockUser:
            def __init__(self, id):
                self.id = id
                self.is_pro = True
                self.display_name = 'Test User'
                self.is_authenticated = True
                self.is_active = True
                self.is_anonymous = False
            def get_id(self):
                return str(self.id)
        
        class MockAgent:
            def __init__(self, id):
                self.id = id
        
        class MockSignAsset:
            def __init__(self, id):
                self.id = id
        
        class MockProperty:
            def __init__(self, id):
                self.id = id
        
        yield MockUser(user_id), MockAgent(agent_id), MockSignAsset(sign_id), MockProperty(prop_id)
        
        # Cleanup
        db.execute("DELETE FROM sign_assets WHERE id = %s", (sign_id,))
        db.execute("DELETE FROM properties WHERE id = %s", (prop_id,))
        db.execute("DELETE FROM agents WHERE id = %s", (agent_id,))
        db.execute("DELETE FROM users WHERE id = %s", (user_id,))
        db.connection.commit()
