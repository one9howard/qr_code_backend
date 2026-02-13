"""
Pytest fixtures for InSite Signs tests.

Provides properly configured test fixtures with real password hashes
and database session management.
"""
import os
import pytest
from werkzeug.security import generate_password_hash

# Set test environment before importing app
os.environ['FLASK_ENV'] = 'testing'
os.environ['DATABASE_URL'] = os.environ.get('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/insite_test')
os.environ['SECRET_KEY'] = 'test-secret-key'
os.environ['STRIPE_SECRET_KEY'] = 'sk_test_mock'
os.environ['PUBLIC_BASE_URL'] = 'http://localhost:8080'
os.environ['STORAGE_BACKEND'] = 'local'


@pytest.fixture(scope='session')
def app():
    """Create application for testing."""
    from app import app as flask_app
    flask_app.config['TESTING'] = True
    flask_app.config['WTF_CSRF_ENABLED'] = False
    flask_app.config['SERVER_NAME'] = 'localhost:8080'
    return flask_app


@pytest.fixture(scope='function')
def client(app):
    """Create a test client for the app."""
    return app.test_client()


@pytest.fixture(scope='function')
def db_session(app):
    """Provide a database session for tests."""
    from database import get_db
    with app.app_context():
        conn = get_db()
        yield conn
        conn.rollback()


@pytest.fixture
def test_user_password():
    """Return a consistent test password."""
    return 'TestPassword123!'


@pytest.fixture
def test_user_password_hash(test_user_password):
    """Return a properly hashed password for test users."""
    return generate_password_hash(test_user_password)


@pytest.fixture
def create_test_user(db_session, test_user_password_hash):
    """Factory fixture to create test users with proper password hashes."""
    created_ids = []
    
    def _create_user(email='test@example.com', is_admin=False, is_verified=True):
        cursor = db_session.cursor()
        cursor.execute(
            """
            INSERT INTO users (email, password_hash, is_admin, is_verified)
            VALUES (%s, %s, %s, %s)
            RETURNING id
            """,
            (email, test_user_password_hash, is_admin, is_verified)
        )
        user_id = cursor.fetchone()['id']
        db_session.commit()
        created_ids.append(user_id)
        return user_id
    
    yield _create_user
    
    # Cleanup
    for user_id in created_ids:
        db_session.execute("DELETE FROM users WHERE id = %s", (user_id,))
    db_session.commit()
