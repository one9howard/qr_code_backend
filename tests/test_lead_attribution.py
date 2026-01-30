"""
Tests for Phase 1: SmartSign Lead Attribution

Tests:
A) Lead validation (email OR phone)
B) Attribution cookie set only on assigned SmartSigns
C) Valid token creates proper attribution
D) Forged tokens are rejected
"""
import pytest
import time
from flask import url_for
from utils.attrib import make_attrib_token, verify_attrib_token


class TestAttribToken:
    """Unit tests for attribution token utilities."""
    
    def test_make_verify_token_roundtrip(self):
        """Token created can be verified."""
        secret = "test-secret-key"
        asset_id = 42
        issued_at = int(time.time())
        
        token = make_attrib_token(asset_id, issued_at, secret)
        result = verify_attrib_token(token, secret, max_age_seconds=60)
        
        assert result == asset_id
    
    def test_expired_token_rejected(self):
        """Expired token returns None."""
        secret = "test-secret-key"
        asset_id = 42
        # Token issued 2 hours ago
        issued_at = int(time.time()) - 7200
        
        token = make_attrib_token(asset_id, issued_at, secret)
        # Max age is 1 hour
        result = verify_attrib_token(token, secret, max_age_seconds=3600)
        
        assert result is None
    
    def test_forged_signature_rejected(self):
        """Token with wrong signature is rejected."""
        secret = "test-secret-key"
        asset_id = 42
        issued_at = int(time.time())
        
        token = make_attrib_token(asset_id, issued_at, secret)
        # Tamper with signature
        parts = token.split('.')
        parts[2] = 'forgedsignature000000000000000'
        forged = '.'.join(parts)
        
        result = verify_attrib_token(forged, secret, max_age_seconds=3600)
        assert result is None
    
    def test_forged_asset_id_rejected(self):
        """Token with modified asset_id is rejected."""
        secret = "test-secret-key"
        asset_id = 42
        issued_at = int(time.time())
        
        token = make_attrib_token(asset_id, issued_at, secret)
        # Change asset_id
        parts = token.split('.')
        parts[0] = '99'
        forged = '.'.join(parts)
        
        result = verify_attrib_token(forged, secret, max_age_seconds=3600)
        assert result is None
    
    def test_invalid_token_formats(self):
        """Various invalid token formats."""
        secret = "test-secret"
        
        assert verify_attrib_token("", secret, 3600) is None
        assert verify_attrib_token("invalid", secret, 3600) is None
        assert verify_attrib_token("1.2", secret, 3600) is None  # Missing sig
        assert verify_attrib_token("not.an.integer", secret, 3600) is None
        assert verify_attrib_token(None, secret, 3600) is None


class TestLeadValidation:
    """Integration tests for lead submission validation."""
    
    @pytest.fixture
    def client(self, app):
        """Flask test client."""
        return app.test_client()
    
    @pytest.fixture
    def app(self):
        """Flask app for testing."""
        from app import create_app
        app = create_app()
        app.config['TESTING'] = True
        return app
    
    @pytest.fixture
    def property_id(self, app):
        """Create a test property and return its ID."""
        from database import get_db
        with app.app_context():
            db = get_db()
            # Find an existing property to use
            row = db.execute("SELECT id FROM properties LIMIT 1").fetchone()
            if row:
                return row['id']
        return None
    
    def test_lead_with_email_only(self, client, property_id):
        """Lead with email only should succeed."""
        if not property_id:
            pytest.skip("No test property available")
        
        response = client.post('/api/leads/submit', json={
            'property_id': property_id,
            'buyer_email': 'test@example.com',
            'consent': True
        })
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
    
    def test_lead_with_phone_only(self, client, property_id):
        """Lead with phone only should succeed."""
        if not property_id:
            pytest.skip("No test property available")
        
        response = client.post('/api/leads/submit', json={
            'property_id': property_id,
            'buyer_phone': '555-123-4567',
            'consent': True
        })
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
    
    def test_lead_without_contact_fails(self, client, property_id):
        """Lead without email OR phone should fail."""
        if not property_id:
            pytest.skip("No test property available")
        
        response = client.post('/api/leads/submit', json={
            'property_id': property_id,
            'buyer_name': 'Test User',
            'consent': True
        })
        
        assert response.status_code == 400
        data = response.get_json()
        assert data['error'] == 'Email or phone is required'


class TestAttributionCookie:
    """Integration tests for attribution cookie behavior."""
    
    @pytest.fixture
    def app(self):
        """Flask app for testing."""
        from app import create_app
        app = create_app()
        app.config['TESTING'] = True
        return app
    
    @pytest.fixture
    def client(self, app):
        """Flask test client."""
        return app.test_client()
    
    def test_cookie_set_on_assigned_smartsign(self, client, app):
        """Attribution cookie is set when scanning assigned SmartSign."""
        from database import get_db
        with app.app_context():
            db = get_db()
            # Find an assigned SmartSign
            asset = db.execute("""
                SELECT sa.code 
                FROM sign_assets sa 
                WHERE sa.active_property_id IS NOT NULL 
                AND sa.activated_at IS NOT NULL
                LIMIT 1
            """).fetchone()
            
            if not asset:
                pytest.skip("No assigned SmartSign available")
            
            response = client.get(f"/r/{asset['code']}", follow_redirects=False)
            
            # Should redirect
            assert response.status_code == 302
            
            # Should have attribution cookie
            cookies = {c.name: c for c in client.cookie_jar}
            assert 'smart_attrib' in cookies
    
    def test_cookie_not_set_on_unassigned_smartsign(self, client, app):
        """Attribution cookie is NOT set when scanning unassigned SmartSign."""
        from database import get_db
        with app.app_context():
            db = get_db()
            # Find an unassigned SmartSign
            asset = db.execute("""
                SELECT sa.code 
                FROM sign_assets sa 
                WHERE sa.active_property_id IS NULL 
                AND sa.activated_at IS NOT NULL
                LIMIT 1
            """).fetchone()
            
            if not asset:
                pytest.skip("No unassigned SmartSign available")
            
            response = client.get(f"/r/{asset['code']}", follow_redirects=False)
            
            # Should render unassigned page
            assert response.status_code == 200
            
            # Should NOT have attribution cookie
            cookies = {c.name: c for c in client.cookie_jar}
            assert 'smart_attrib' not in cookies


class TestLeadAttribution:
    """Integration tests for lead attribution flow."""
    
    @pytest.fixture
    def app(self):
        """Flask app for testing."""
        from app import create_app
        app = create_app()
        app.config['TESTING'] = True
        return app
    
    @pytest.fixture
    def client(self, app):
        """Flask test client."""
        return app.test_client()
    
    def test_lead_attributed_with_valid_token(self, client, app):
        """Lead is attributed when valid token present."""
        from database import get_db
        from config import SECRET_KEY
        
        with app.app_context():
            db = get_db()
            
            # Find an asset and property
            asset = db.execute("""
                SELECT sa.id, sa.active_property_id
                FROM sign_assets sa 
                WHERE sa.active_property_id IS NOT NULL
                LIMIT 1
            """).fetchone()
            
            if not asset:
                pytest.skip("No assigned SmartSign available")
            
            # Create valid token
            token = make_attrib_token(asset['id'], int(time.time()), SECRET_KEY)
            
            # Set cookie
            client.set_cookie('localhost', 'smart_attrib', token)
            
            # Submit lead
            response = client.post('/api/leads/submit', json={
                'property_id': asset['active_property_id'],
                'buyer_email': f'test{int(time.time())}@example.com',
                'consent': True
            })
            
            assert response.status_code == 200
            
            # Check lead was attributed
            lead = db.execute("""
                SELECT sign_asset_id, source 
                FROM leads 
                WHERE property_id = %s 
                ORDER BY created_at DESC 
                LIMIT 1
            """, (asset['active_property_id'],)).fetchone()
            
            assert lead['sign_asset_id'] == asset['id']
            assert lead['source'] == 'smart_sign'
    
    def test_forged_token_ignored(self, client, app):
        """Forged token is ignored, lead marked as direct."""
        from database import get_db
        
        with app.app_context():
            db = get_db()
            
            # Find a property
            prop = db.execute("SELECT id FROM properties LIMIT 1").fetchone()
            if not prop:
                pytest.skip("No property available")
            
            # Set forged cookie
            client.set_cookie('localhost', 'smart_attrib', '999.12345.forgedsig0000000000000')
            
            # Submit lead
            response = client.post('/api/leads/submit', json={
                'property_id': prop['id'],
                'buyer_email': f'forged{int(time.time())}@example.com',
                'consent': True
            })
            
            assert response.status_code == 200
            
            # Check lead was NOT attributed
            lead = db.execute("""
                SELECT sign_asset_id, source 
                FROM leads 
                WHERE property_id = %s 
                ORDER BY created_at DESC 
                LIMIT 1
            """, (prop['id'],)).fetchone()
            
            assert lead['sign_asset_id'] is None
            assert lead['source'] == 'direct'
