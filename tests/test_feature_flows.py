import pytest
import secrets
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
from werkzeug.security import generate_password_hash

# --- Fixtures for Feature Flows ---

@pytest.fixture
def feature_data(db):
    """Setup users/agents for feature tests."""
    password = "password123"
    p_hash = generate_password_hash(password)

    # User 1 (Owner)
    user_id = db.execute(
        "INSERT INTO users (email, password_hash, is_verified) VALUES (%s, %s, %s) RETURNING id",
        ('owner@feature.com', p_hash, True)
    ).fetchone()['id']

    # Agent
    agent_id = db.execute(
        "INSERT INTO agents (user_id, name, brokerage, email, phone) VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (user_id, 'Feature Agent', 'Brokerage', 'agent@feature.com', '555-1111')
    ).fetchone()['id']

    db.commit()
    return {'user_id': user_id, 'agent_id': agent_id, 'email': 'owner@feature.com', 'password': password}


# --- Lead Lifecycle ---

def test_lead_lifecycle(client, db, feature_data):
    """Test full lead lifecycle: creation, notes, status change."""
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)

    # Create Property (must be active/unexpired)
    prop_id = db.execute(
        """INSERT INTO properties (agent_id, address, beds, baths, slug, price, qr_code, expires_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
           RETURNING id""",
        (feature_data['agent_id'], '123 Lead St', '3', '2', 'lead-st', '$500k', 'LEAD123', expires_at)
    ).fetchone()['id']
    db.commit()

    # 1. Create Lead
    response = client.post("/api/leads/submit", json={
        "property_id": prop_id,
        "buyer_name": "Lead Test",
        "buyer_email": "lead@test.com",
        "consent": True
    })
    assert response.status_code == 200

    lead = db.execute("SELECT * FROM leads WHERE buyer_email = 'lead@test.com'").fetchone()
    assert lead is not None
    assert lead['status'] == 'new'
    lead_id = lead['id']

    # Login as owner
    login_resp = client.post("/login", data={
        "email": feature_data['email'],
        "password": feature_data['password']
    }, follow_redirects=True)
    assert login_resp.status_code == 200

    # 2. Add Note (lead_management.add_note returns redirect)
    response = client.post(f"/api/leads/{lead_id}/notes", data={"body": "Test Note"})
    assert response.status_code == 302
    assert f"/dashboard/leads/{lead_id}" in response.location
    
    # Ensure we see the changes from the other connection
    db.commit()

    notes = db.execute("SELECT * FROM lead_notes WHERE lead_id = %s", (lead_id,)).fetchall()
    assert len(notes) == 1
    assert notes[0]['body'] == "Test Note"

    # Verify Audit Log
    events = db.execute("SELECT * FROM lead_events WHERE lead_id = %s AND event_type = 'note_added'", (lead_id,)).fetchall()
    assert len(events) == 1

    # 3. Update Status
    response = client.post(f"/api/leads/{lead_id}/status", data={"status": "contacted"})
    assert response.status_code == 200
    assert response.json['success'] is True
    
    db.commit()
    lead = db.execute("SELECT status FROM leads WHERE id = %s", (lead_id,)).fetchone()
    assert lead['status'] == 'contacted'


# --- QR Variants ---

def test_qr_variant_resolution(client, db, feature_data):
    """Test standard QR vs Variant QR resolution."""
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)

    # Setup Property with Legacy Code (must be active/unexpired)
    prop_id = db.execute(
        """INSERT INTO properties (agent_id, address, beds, baths, slug, qr_code, expires_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
        (feature_data['agent_id'], '456 Variant St', '3', '2', 'variant-st', 'LEGACY123', expires_at)
    ).fetchone()['id']

    # Create Campaign & Variant
    camp_id = db.execute(
        "INSERT INTO campaigns (property_id, name) VALUES (%s, %s) RETURNING id",
        (prop_id, 'Flyer Campaign')
    ).fetchone()['id']

    db.execute(
        "INSERT INTO qr_variants (property_id, campaign_id, code, label) VALUES (%s, %s, 'VARIANT456', 'Flyer A')",
        (prop_id, camp_id)
    )
    db.commit()

    # 1. Test Legacy Code
    response = client.get("/r/LEGACY123", follow_redirects=False)
    assert response.status_code == 302
    assert "variant-st" in response.location

    # 2. Test Variant Code
    response = client.get("/r/VARIANT456", follow_redirects=False)
    assert response.status_code == 302
    assert "variant-st" in response.location

    # Verify Scan Logging
    scan = db.execute("SELECT * FROM qr_scans WHERE qr_variant_id IS NOT NULL").fetchone()
    assert scan is not None


# --- Open House Mode ---

def test_open_house_mode(client, db, feature_data):
    """Test that Open House mode renders correctly."""
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)

    prop_id = db.execute(
        """INSERT INTO properties (agent_id, address, beds, baths, slug, qr_code, expires_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
        (feature_data['agent_id'], '789 Open St', '3', '2', 'open-st', 'OPEN123', expires_at)
    ).fetchone()['id']
    db.commit()

    # Normal View
    response = client.get("/p/open-st")
    assert response.status_code == 200
    assert b"Open House Check-In" not in response.data

    # Open House View
    response = client.get("/p/open-st?mode=open_house")
    assert response.status_code == 200
    assert b"Open House Check-In" in response.data


# --- Gating Render ---

def test_gating_rendering(client, db, feature_data):
    """Test unpaid vs paid property page rendering."""
    # Paid Property (via subscription)
    pro_user_id = db.execute(
        "INSERT INTO users (email, password_hash, is_verified, subscription_status) VALUES (%s, %s, %s, %s) RETURNING id",
        ('pro_render@test.com', 'hash', True, 'active')
    ).fetchone()['id']

    pro_agent_id = db.execute(
        "INSERT INTO agents (user_id, email, name, brokerage) VALUES (%s, %s, %s, %s) RETURNING id",
        (pro_user_id, 'pro_render@test.com', 'Pro', 'Brokerage')
    ).fetchone()['id']

    # Pro Property: expired timestamp is OK because subscription overrides expiry
    pro_prop_slug = 'pro-render-slug'
    db.execute(
        """INSERT INTO properties (agent_id, address, beds, baths, slug, qr_code, expires_at)
           VALUES (%s, 'Pro St', '3', '2', %s, %s, '2020-01-01 00:00:00+00')""",
        (pro_agent_id, pro_prop_slug, 'PROQR123')
    )

    # Unpaid Property: expired -> 410
    unpaid_prop_slug = 'unpaid-render-slug'
    db.execute(
        """INSERT INTO properties (agent_id, address, beds, baths, slug, qr_code, expires_at)
           VALUES (%s, 'Free St', '3', '2', %s, %s, '2020-01-01 00:00:00+00')""",
        (feature_data['agent_id'], unpaid_prop_slug, 'FREEQR123')
    )
    db.commit()

    # 1. Unpaid Page logic (Expired -> 410)
    response = client.get(f"/p/{unpaid_prop_slug}")
    assert response.status_code == 410

    # 2. Paid Page (Subs)
    response = client.get(f"/p/{pro_prop_slug}")
    assert response.status_code == 200
    html = response.data.decode()
    assert 'class="gallery"' in html or 'description-box' in html


# --- Cleanup ---

@patch('utils.storage.get_storage')
def test_cleanup_calls_storage_delete(mock_get_storage, db):
    """Cleanup should call storage.delete for each photo."""
    mock_storage = MagicMock()
    mock_get_storage.return_value = mock_storage

    # Setup Data
    user_id = db.execute(
        "INSERT INTO users (email, password_hash) VALUES (%s, %s) RETURNING id",
        ('cleanup@test.com', 'hash')
    ).fetchone()['id']

    agent_id = db.execute(
        "INSERT INTO agents (user_id, email, name, brokerage) VALUES (%s, %s, %s, %s) RETURNING id",
        (user_id, 'clean@test.com', 'Clean', 'Brokerage')
    ).fetchone()['id']

    expired_time = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(sep=' ')
    slug = f"cleanup-test-{secrets.token_hex(4)}"
    qr_code = secrets.token_hex(6)

    prop_id = db.execute(
        "INSERT INTO properties (agent_id, address, beds, baths, slug, qr_code, expires_at) VALUES (%s, 'Clean', 1, 1, %s, %s, %s) RETURNING id",
        (agent_id, slug, qr_code, expired_time)
    ).fetchone()['id']

    db.execute(
        "INSERT INTO property_photos (property_id, filename) VALUES (%s, 'uploads/test.jpg')",
        (prop_id,)
    )
    db.commit()

    from services.cleanup import cleanup_expired_properties
    cleanup_expired_properties()

    # Verify storage.delete matched uploads/test.jpg
    found = False
    for call in mock_storage.delete.call_args_list:
        if 'uploads/test.jpg' in str(call):
            found = True
            break
    assert found, "Expected delete call for uploads/test.jpg"
