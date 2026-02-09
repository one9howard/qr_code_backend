import pytest
from flask import url_for

def test_dashboard_new_property_page_loads(client, app):
    """
    Simulate a user visiting /dashboard/properties/new.
    This should render the 'dashboard/property_new.html' template.
    Failures here typically indicate TemplateNotFound or context errors.
    """
    # 1. Login as a user
    # The conftest.py likely sets up a DB, but we need a user.
    # We can mock login or create a user.
    # Let's inspect how other tests do it or just create a user.
    
    from models import User, Agent
    from database import get_db
    
    with app.app_context():
        db = get_db()
        # Create user
        u = User(
            email="test_repro@example.com", 
            auth_provider="email", 
            auth_provider_id="test_repro"
        )
        u.save()
        
        # Create agent for this user (needed for some dashboard logic)
        db.execute(
            "INSERT INTO agents (user_id, name, email) VALUES (%s, %s, %s)",
            (u.id, "Test Agent", "test_repro@example.com")
        )
        db.commit()
        
        user_id = u.id

    # 2. Login via session (simplest if login_manager is standard)
    # Alternatively, use flask_login's test_client integration if available,
    # but setting the session manually is robust.
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user_id)
        sess['_fresh'] = True

    # 3. Request the page
    resp = client.get('/dashboard/properties/new')
    
    # 4. Assert success
    assert resp.status_code == 200, f"Expected 200 OK, got {resp.status_code}. Data: {resp.data.decode()}"
    assert b"Create Property" in resp.data
