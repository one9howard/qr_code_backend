
import pytest
from werkzeug.security import generate_password_hash
from PIL import Image
import io
import uuid       

@pytest.fixture
def free_user(db):
    email = f"free-{uuid.uuid4()}@example.com"
    pwd = "password123"
    db.execute("""
        INSERT INTO users (email, password_hash, subscription_status, is_verified, full_name)
        VALUES (%s, %s, 'canceled', TRUE, 'Free User')
    """, (email, generate_password_hash(pwd)))
    db.commit()
    user = db.execute("SELECT * FROM users WHERE email = %s", (email,)).fetchone()
    return dict(user)

@pytest.fixture
def pro_user(db):
    email = f"pro-{uuid.uuid4()}@example.com"
    pwd = "password123"
    db.execute("""
        INSERT INTO users (email, password_hash, subscription_status, is_verified, full_name)
        VALUES (%s, %s, 'active', TRUE, 'Pro User')
    """, (email, generate_password_hash(pwd)))
    db.commit()
    user = db.execute("SELECT * FROM users WHERE email = %s", (email,)).fetchone()
    return dict(user)

def login(client, email, password="password123"):
    """Helper to login and handle redirects."""
    # Avoid rate-limiter drift across the suite by forcing session auth.
    from app import app as flask_app
    with flask_app.app_context():
        from database import get_db
        row = get_db().execute("SELECT id FROM users WHERE email = %s", (email,)).fetchone()
        assert row is not None, f"User not found for login helper: {email}"
        user_id = row['id']

    with client.session_transaction() as sess:
        sess['_user_id'] = str(user_id)
        sess['_fresh'] = True

def test_qr_logo_gating_free_user(client, free_user):
    # 1. Login
    login(client, free_user['email'])
    
    # 2. Upload -> 403
    logo_file = (io.BytesIO(b"fake data"), 'logo.png')
    resp = client.post('/api/branding/qr-logo', data={'logo': logo_file}, 
                      content_type='multipart/form-data')
    assert resp.status_code == 403
    assert resp.json['error'] == 'pro_required'
    
    # 3. Toggle ON -> 403
    resp = client.post('/api/branding/qr-logo/toggle', json={'use_qr_logo': True})
    assert resp.status_code == 403
    
    # 4. Toggle OFF -> 200 (Allowed)
    resp = client.post('/api/branding/qr-logo/toggle', json={'use_qr_logo': False})
    assert resp.status_code == 200
    
    # 5. Delete -> 200 (Allowed cleanup)
    resp = client.delete('/api/branding/qr-logo')
    assert resp.status_code == 200

def test_qr_logo_flow_pro_user(client, pro_user, db):
    # 1. Login
    login(client, pro_user['email'])
    
    # Need a valid image for validation step (server-side pillow check)
    img = Image.new('RGB', (100, 100), color='red')
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    
    # 2. Upload -> 200
    resp = client.post('/api/branding/qr-logo', data={'logo': (buf, 'logo.png')},
                      content_type='multipart/form-data')
    assert resp.status_code == 200, f"Response: {resp.text}"
    assert resp.json['ok'] is True
    
    # Verify DB populated
    row = db.execute("SELECT qr_logo_original_key, qr_logo_normalized_key FROM users WHERE id = %s", (pro_user['id'],)).fetchone()
    assert row['qr_logo_original_key'] is not None
    assert row['qr_logo_normalized_key'] is not None
    
    # 3. Toggle ON -> 200
    resp = client.post('/api/branding/qr-logo/toggle', json={'use_qr_logo': True})
    assert resp.status_code == 200
    assert resp.json['use_qr_logo'] is True
    
    # Verify DB toggle
    row = db.execute("SELECT use_qr_logo FROM users WHERE id = %s", (pro_user['id'],)).fetchone()
    assert row['use_qr_logo'] is True
    
    # 4. Delete -> 200
    resp = client.delete('/api/branding/qr-logo')
    assert resp.status_code == 200
    
    # Verify DB cleanup
    row = db.execute("SELECT qr_logo_original_key, use_qr_logo FROM users WHERE id = %s", (pro_user['id'],)).fetchone()
    assert row['qr_logo_original_key'] is None
    assert row['use_qr_logo'] is False
