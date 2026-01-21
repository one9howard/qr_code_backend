"""
Admin Metrics Tests

Tests for the admin metrics page.
"""
import pytest
from werkzeug.security import generate_password_hash


@pytest.fixture
def admin_user(db):
    """Create an admin user for testing."""
    hashed_pw = generate_password_hash('adminpass')
    
    admin_id = db.execute(
        "INSERT INTO users (email, password_hash, is_verified, is_admin) VALUES (%s, %s, %s, %s) RETURNING id",
        ('admin@metrics.test', hashed_pw, True, True)
    ).fetchone()['id']
    
    db.commit()
    
    return {
        'id': admin_id,
        'email': 'admin@metrics.test',
        'password': 'adminpass'
    }


def test_admin_metrics_page_loads(client, db, admin_user):
    """Admin can access metrics page and it contains expected heading."""
    # Login as admin
    client.post('/login', data={'email': admin_user['email'], 'password': admin_user['password']})
    
    # Access metrics page
    resp = client.get('/admin/metrics')
    
    assert resp.status_code == 200
    assert b'Admin Metrics' in resp.data
    assert b'Last 7 days' in resp.data


def test_non_admin_cannot_access_metrics(client, db):
    """Non-admin user cannot access the metrics page."""
    # Create non-admin user
    hashed_pw = generate_password_hash('userpass')
    db.execute(
        "INSERT INTO users (email, password_hash, is_verified, is_admin) VALUES (%s, %s, %s, %s)",
        ('user@metrics.test', hashed_pw, True, False)
    )
    db.commit()
    
    # Login as regular user
    client.post('/login', data={'email': 'user@metrics.test', 'password': 'userpass'})
    
    # Attempt to access metrics page
    resp = client.get('/admin/metrics')
    
    # Should be forbidden
    assert resp.status_code == 403
