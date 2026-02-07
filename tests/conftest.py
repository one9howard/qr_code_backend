"""
Shared pytest fixtures for InSite Signs test suite.

Provides common fixtures for:
- app: Flask application with test config
- client: Flask test client
- db: Database connection with auto-cleanup
"""
import pytest
from app import create_app
from database import get_db


@pytest.fixture(scope='function')
def app():
    """Create Flask app with test configuration."""
    app = create_app({
        'TESTING': True,
        'SERVER_NAME': 'localhost',
        'WTF_CSRF_ENABLED': False,
    })
    yield app


@pytest.fixture(scope='function')
def client(app):
    """Flask test client."""
    return app.test_client()


@pytest.fixture(scope='function')
def db(app):
    """Database connection with auto-cleanup.
    
    Wraps test in a transaction that gets rolled back after each test
    to ensure test isolation without leaving test data behind.
    """
    with app.app_context():
        connection = get_db()
        yield connection
        # Note: Most test files commit their own transactions. 
        # Cleanup happens via explicit DELETE statements or table truncation.


@pytest.fixture
def runner(app):
    """Flask CLI test runner."""
    return app.test_cli_runner()


@pytest.fixture
def auth_session(client, db):
    """Helper to create authenticated session for a test user.
    
    Creates a user and logs them in via session manipulation.
    Returns (user_id, agent_id) tuple.
    """
    # Create user
    db.execute("""
        INSERT INTO users (email, password_hash, subscription_status)
        VALUES ('auth_test@example.com', 'hash', 'active')
        ON CONFLICT (email) DO UPDATE SET subscription_status = 'active'
    """)
    user = db.execute("SELECT id FROM users WHERE email = 'auth_test@example.com'").fetchone()
    user_id = user['id']
    
    # Create agent (cleanup first)
    db.execute("DELETE FROM agents WHERE email = 'auth_test@example.com'")
    db.execute("""
        INSERT INTO agents (user_id, name, email, brokerage)
        VALUES (%s, 'Auth Test Agent', 'auth_test@example.com', 'Test Brokerage')
    """, (user_id,))
    agent = db.execute("SELECT id FROM agents WHERE user_id = %s", (user_id,)).fetchone()
    agent_id = agent['id']
    
    db.commit()
    
    # Set session
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user_id)
        sess['_fresh'] = True
    
    return user_id, agent_id
