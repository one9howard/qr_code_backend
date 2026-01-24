"""
Test that /api/events is CSRF-exempt for public property pages.

This test verifies the events endpoint works without a CSRF token,
which is required for client-side event tracking on public pages.
"""
import pytest


def test_events_endpoint_accepts_post_without_csrf(client, db):
    """
    Verify /api/events accepts POST without explicit CSRF token.
    
    Note: The test fixture may disable CSRF globally, so this test mainly
    verifies the endpoint logic works and stores events correctly.
    The csrf.exempt(events_bp) in app.py is what enables production use.
    """
    # Setup minimal data - need property for events
    db.execute("""
        INSERT INTO users (email, password_hash, is_verified) 
        VALUES ('event_test@test.com', 'x', true)
    """)
    user_id = db.execute(
        "SELECT id FROM users WHERE email='event_test@test.com'"
    ).fetchone()[0]
    
    db.execute("""
        INSERT INTO agents (user_id, email, name, brokerage) 
        VALUES (%s, 'event@agent.com', 'Event Agent', 'Brokerage')
    """, (user_id,))
    agent_id = db.execute("SELECT id FROM agents WHERE user_id=%s", (user_id,)).fetchone()[0]
    
    db.execute("""
        INSERT INTO properties (agent_id, address, beds, baths, slug, qr_code) 
        VALUES (%s, '123 Event St', '2', '1', 'event-test', 'eventcode123')
    """, (agent_id,))
    prop_id = db.execute("SELECT id FROM properties WHERE agent_id=%s", (agent_id,)).fetchone()[0]
    db.commit()
    
    # Make the POST request (no CSRF token in headers)
    response = client.post(
        '/api/events',
        json={
            "event_type": "cta_click",
            "property_id": prop_id,
            "payload": {"ui": "test", "tier": "paid"}
        },
        content_type="application/json"
    )
    
    # Assert success - should NOT get 400 CSRF error
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.data}"
    data = response.get_json()
    assert data.get("success") is True, f"Expected success=True, got: {data}"
    
    # Verify the event was actually stored (use occurred_at, not created_at)
    event = db.execute("""
        SELECT event_type, source, property_id 
        FROM app_events 
        WHERE event_type = 'cta_click' 
        ORDER BY occurred_at DESC LIMIT 1
    """).fetchone()
    
    assert event is not None, "Event should be stored in app_events"
    assert event['event_type'] == 'cta_click'
    assert event['source'] == 'client'
    assert event['property_id'] == prop_id


def test_events_blueprint_is_csrf_exempt_in_app():
    """
    Verify that events_bp is exempted from CSRF in app.py.
    This is a simple code inspection test.
    """
    import inspect
    import app as app_module
    
    source = inspect.getsource(app_module.create_app)
    
    # Check that csrf.exempt(events_bp) is present
    assert 'csrf.exempt(events_bp)' in source, \
        "events_bp should be exempted from CSRF in app.py create_app()"
