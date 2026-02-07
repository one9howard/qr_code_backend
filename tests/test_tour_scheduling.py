import pytest
from app import create_app
from database import get_db

@pytest.fixture
def app():
    app = create_app(test_config={'TESTING': True})
    return app

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def auth(client):
    from flask_login import login_user
    # Mock auth helper if needed
    pass

def test_tour_scheduling_link_render(client, app):
    """Test that public property page renders the scheduling link when present."""
    with app.app_context():
        db = get_db()
        # Setup data
        # 1. Create User
        db.execute("INSERT INTO users (email, password_hash, subscription_status) VALUES ('agent@test.com', 'hash', 'active')")
        user = db.execute("SELECT * FROM users WHERE email='agent@test.com'").fetchone()
        
        # 2. Create Agent with Scheduling URL
        db.execute(
            "INSERT INTO agents (user_id, name, email, brokerage, scheduling_url) VALUES (%s, 'Test Agent', 'agent@test.com', 'Test Brokerage', 'https://calendly.com/test')",
            (user['id'],)
        )
        agent = db.execute("SELECT * FROM agents WHERE user_id=%s", (user['id'],)).fetchone()
        
        # 3. Create Property
        db.execute(
            "INSERT INTO properties (agent_id, address, slug, created_at, virtual_tour_url) VALUES (%s, '123 Test St', 'test-prop', '2025-01-01', 'https://matterport.com/test')",
            (agent['id'],)
        )
        
    # Request page
    response = client.get('/p/test-prop')
    assert response.status_code == 200
    html = response.data.decode()
    
    # Assert Scheduling Link
    assert 'data-scheduling-url="https://calendly.com/test"' in html
    assert 'Schedule a tour' in html
    
    # Assert Virtual Tour (Paid user)
    assert 'Virtual Tour' in html
    assert 'https://matterport.com/test' in html
    assert 'Open virtual tour' in html

def test_free_tier_hides_virtual_tour(client, app):
    """Test that free tier users see teaser for virtual tour."""
    with app.app_context():
        db = get_db()
        # 1. Create Free User
        db.execute("INSERT INTO users (email, password_hash, subscription_status) VALUES ('free@test.com', 'hash', 'free')")
        user = db.execute("SELECT * FROM users WHERE email='free@test.com'").fetchone()
        
        # 2. Create Agent
        db.execute("INSERT INTO agents (user_id, name, email, brokerage) VALUES (%s, 'Free Agent', 'free@test.com', 'Free Brokerage')", (user['id'],))
        agent = db.execute("SELECT * FROM agents WHERE user_id=%s", (user['id'],)).fetchone()
        
        # 3. Create Property with Virtual Tour
        db.execute(
            "INSERT INTO properties (agent_id, address, slug, created_at, virtual_tour_url) VALUES (%s, '456 Free St', 'free-prop', '2025-01-01', 'https://matterport.com/secret')",
            (agent['id'],)
        )
        
    response = client.get('/p/free-prop')
    assert response.status_code == 200
    html = response.data.decode()
    
    # Assert Virtual Tour Section is present but mocked/locked
    assert 'Virtual Tour' in html
    assert 'Virtual tour available' in html # Teaser title
    assert 'https://matterport.com/secret' not in html # URL should NOT be leaked
    assert 'Open virtual tour' not in html
