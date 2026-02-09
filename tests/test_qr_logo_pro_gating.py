
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
    # CSRF might be disabled in test config, otherwise need csrf_token
    resp = client.post('/login', data={'email': email, 'password': password}, follow_redirects=True)
    
    # Assert login success
    if b"Invalid email" in resp.data:
        pytest.fail(f"Login failed for {email}: Invalid credentials message found.")
    
    # Check if we are on dashboard or similar (200 OK)
    assert resp.status_code == 200, f"Login return status {resp.status_code}. Location: {resp.headers.get('Location')}"
    return resp

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
