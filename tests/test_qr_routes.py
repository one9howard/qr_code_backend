"""
QR Route Regression Tests

Tests for public-facing routes:
- GET /r/<code> - QR scan redirect
- GET /p/<slug> - Property page

These routes are hammered by end-users and must be rock solid.
"""
import pytest
from app import create_app
from database import get_db


@pytest.fixture
def app():
    """Create test app with testing config."""
    app = create_app({
        'TESTING': True,
        'SERVER_NAME': 'localhost',
        'WTF_CSRF_ENABLED': False,
    })
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def setup_test_data(app):
    """Set up test property and agent data."""
    with app.app_context():
        db = get_db()
        
        # Cleanup existing test data first (proper FK order: orders -> properties -> agents -> users)
        db.execute("DELETE FROM orders WHERE property_id IN (SELECT id FROM properties WHERE slug IN ('test-paid-property', 'test-expired-property', 'test-free-property'))")
        db.execute("DELETE FROM qr_scans WHERE property_id IN (SELECT id FROM properties WHERE slug IN ('test-paid-property', 'test-expired-property', 'test-free-property'))")
        db.execute("DELETE FROM property_views WHERE property_id IN (SELECT id FROM properties WHERE slug IN ('test-paid-property', 'test-expired-property', 'test-free-property'))")
        db.execute("DELETE FROM leads WHERE property_id IN (SELECT id FROM properties WHERE slug IN ('test-paid-property', 'test-expired-property', 'test-free-property'))")
        db.execute("DELETE FROM properties WHERE slug IN ('test-paid-property', 'test-expired-property', 'test-free-property')")
        db.execute("DELETE FROM agents WHERE email = 'test@example.com'")
        # Don't delete user since email has unique constraint and we want to reuse
        
        # Create test user (upsert)
        db.execute("""
            INSERT INTO users (email, password_hash, subscription_status)
            VALUES ('test@example.com', 'hash', 'active')
            ON CONFLICT (email) DO UPDATE SET subscription_status = 'active'
        """)
        user = db.execute("SELECT id FROM users WHERE email = 'test@example.com'").fetchone()
        
        # Create test agent
        db.execute("""
            INSERT INTO agents (user_id, name, email, brokerage)
            VALUES (%s, 'Test Agent', 'test@example.com', 'Test Brokerage')
        """, (user['id'],))
        agent = db.execute("SELECT id FROM agents WHERE user_id = %s", (user['id'],)).fetchone()
        
        # Create paid property
        db.execute("""
            INSERT INTO properties (agent_id, address, slug, qr_code, created_at)
            VALUES (%s, '123 Test St', 'test-paid-property', 'TESTPAID001', NOW())
        """, (agent['id'],))
        paid_prop = db.execute("SELECT id FROM properties WHERE slug = 'test-paid-property'").fetchone()
        
        # Create order for paid property
        db.execute("""
            INSERT INTO orders (property_id, user_id, status, order_type, paid_at, created_at)
            VALUES (%s, %s, 'paid', 'sign', NOW(), NOW())
        """, (paid_prop['id'], user['id']))
        
        # Create expired property
        db.execute("""
            INSERT INTO properties (agent_id, address, slug, qr_code, created_at, expires_at)
            VALUES (%s, '456 Expired Ave', 'test-expired-property', 'TESTEXP001', NOW(), NOW() - INTERVAL '1 day')
        """, (agent['id'],))
        
        # Create free property
        db.execute("""
            INSERT INTO properties (agent_id, address, slug, qr_code, created_at)
            VALUES (%s, '789 Free Blvd', 'test-free-property', 'TESTFREE01', NOW())
        """, (agent['id'],))
        
        db.commit()
        
        yield {
            'paid_slug': 'test-paid-property',
            'paid_code': 'TESTPAID001',
            'expired_slug': 'test-expired-property',
            'expired_code': 'TESTEXP001',
            'free_slug': 'test-free-property',
            'free_code': 'TESTFREE01',
        }


class TestPropertyPage:
    """Tests for /p/<slug> route."""
    
    def test_paid_property_returns_200(self, client, setup_test_data):
        """Paid property should return 200 with full content."""
        response = client.get(f'/p/{setup_test_data["paid_slug"]}')
        assert response.status_code == 200
        assert b'123 Test St' in response.data or b'Test Agent' in response.data
    
    def test_expired_property_returns_410(self, client, setup_test_data):
        """Expired property should return 410 Gone."""
        response = client.get(f'/p/{setup_test_data["expired_slug"]}')
        assert response.status_code == 410
    
    def test_invalid_slug_returns_404(self, client):
        """Invalid slug should return 404."""
        response = client.get('/p/nonexistent-property-12345')
        assert response.status_code == 404
    
    def test_free_property_returns_200(self, client, setup_test_data):
        """Free property should return 200 (gated content)."""
        response = client.get(f'/p/{setup_test_data["free_slug"]}')
        # Free properties show content but gated
        assert response.status_code == 200


class TestQRRedirect:
    """Tests for /r/<code> route."""
    
    def test_valid_code_redirects(self, client, setup_test_data):
        """Valid QR code should redirect to property page."""
        response = client.get(f'/r/{setup_test_data["paid_code"]}', follow_redirects=False)
        # Should be 302/301 redirect
        assert response.status_code in (301, 302)
        assert '/p/test-paid-property' in response.headers.get('Location', '')
    
    def test_expired_property_code_returns_410(self, client, setup_test_data):
        """Expired property QR code should return 410."""
        response = client.get(f'/r/{setup_test_data["expired_code"]}')
        assert response.status_code == 410
    
    def test_invalid_code_returns_404(self, client):
        """Invalid QR code should return 404."""
        response = client.get('/r/INVALIDCODE123')
        assert response.status_code == 404
    
    def test_scan_logs_to_qr_scans(self, client, app, setup_test_data):
        """Valid scan should create qr_scans record."""
        with app.app_context():
            db = get_db()
            
            # Get property ID
            prop = db.execute("SELECT id FROM properties WHERE slug = 'test-paid-property'").fetchone()
            
            # Count scans before
            before = db.execute("SELECT COUNT(*) as c FROM qr_scans WHERE property_id = %s", (prop['id'],)).fetchone()
            before_count = before['c']
        
        # Trigger scan
        response = client.get(f'/r/{setup_test_data["paid_code"]}', follow_redirects=False)
        
        with app.app_context():
            db = get_db()
            prop = db.execute("SELECT id FROM properties WHERE slug = 'test-paid-property'").fetchone()
            after = db.execute("SELECT COUNT(*) as c FROM qr_scans WHERE property_id = %s", (prop['id'],)).fetchone()
            after_count = after['c']
        
        assert after_count > before_count, "Scan should be logged to qr_scans table"
