"""
Pytest fixtures for InSite Signs tests.

Provides properly configured test fixtures with real password hashes
and database session management.
"""
import os
import pytest
import psycopg2
from werkzeug.security import generate_password_hash

# Set test environment before importing app
os.environ['FLASK_ENV'] = 'testing'
os.environ['DATABASE_URL'] = os.environ.get('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/insite_test')
os.environ['SECRET_KEY'] = 'test-secret-key'
os.environ['STRIPE_SECRET_KEY'] = 'sk_test_mock'
os.environ['PUBLIC_BASE_URL'] = 'http://localhost:8080'
os.environ['STORAGE_BACKEND'] = 'local'

TEST_RUN_ADVISORY_LOCK_KEY = 972413


@pytest.fixture(scope='session', autouse=True)
def single_test_runner_lock():
    """
    Prevent concurrent pytest sessions against the same DB.
    Concurrent runs are the main source of apparent "stalls" due to lock contention.
    """
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        yield
        return

    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("SELECT pg_try_advisory_lock(%s)", (TEST_RUN_ADVISORY_LOCK_KEY,))
    locked = bool(cur.fetchone()[0])
    if not locked:
        cur.close()
        conn.close()
        pytest.exit(
            "Another pytest process is already using this database. "
            "Stop the existing run before starting a new one.",
            returncode=2
        )

    try:
        yield
    finally:
        try:
            cur.execute("SELECT pg_advisory_unlock(%s)", (TEST_RUN_ADVISORY_LOCK_KEY,))
        finally:
            cur.close()
            conn.close()


def _truncate_all_tables(db):
    """
    Truncate all public tables except Alembic metadata.
    This guarantees test isolation even when tests call commit().
    """
    # Defensive cleanup: interrupted runs can leave idle-in-transaction sessions
    # that block TRUNCATE via lingering relation locks.
    db.execute(
        """
        SELECT pg_terminate_backend(pid)
        FROM pg_stat_activity
        WHERE datname = current_database()
          AND pid <> pg_backend_pid()
          AND state = 'idle in transaction'
        """
    )
    db.commit()

    # Ensure we fail fast on lock issues instead of hanging for minutes.
    db.execute("SET lock_timeout = '5s'")

    rows = db.execute(
        """
        SELECT tablename
        FROM pg_tables
        WHERE schemaname = 'public'
          AND tablename <> 'alembic_version'
        ORDER BY tablename
        """
    ).fetchall()

    tables = [r['tablename'] for r in rows]
    if not tables:
        return

    quoted = ", ".join(f'"{t}"' for t in tables)
    db.execute(f"TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE")
    db.commit()


@pytest.fixture(scope='session')
def app():
    """Create application for testing."""
    from app import app as flask_app
    flask_app.config['TESTING'] = True
    flask_app.config['WTF_CSRF_ENABLED'] = False
    flask_app.config['SERVER_NAME'] = 'localhost:8080'
    return flask_app


@pytest.fixture(scope='function', autouse=True)
def clean_database(app):
    """Hard reset DB before each test for isolation."""
    from database import get_db
    with app.app_context():
        _truncate_all_tables(get_db())


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
        try:
            conn.rollback()
        except Exception:
            pass


@pytest.fixture(scope='function')
def db(db_session):
    """
    Alias for db_session with added compatibility layer.
    Wraps the raw PostgresDB connection to provide a .session attribute
    and .add() method, mimicking SQLAlchemy for legacy tests.
    """
    class SessionProxy:
        def __init__(self, db_conn):
            self.db_conn = db_conn
        
        def __getattr__(self, name):
            return getattr(self.db_conn, name)
            
        @property
        def session(self):
            return self
            
        def add(self, obj):
            if hasattr(obj, 'save'):
                obj.save()
                
    return SessionProxy(db_session)


@pytest.fixture
def auth(client, db):
    """Authentication helper for tests that need login."""
    class AuthActions:
        def __init__(self, client, db):
            self._client = client
            self._db = db

        def login(self, email='test@example.com', password='TestPassword123!'):
            # Ensure user exists
            from werkzeug.security import generate_password_hash
            existing = self._db.execute(
                "SELECT id FROM users WHERE email = %s", (email,)
            ).fetchone()
            if not existing:
                self._db.execute(
                    "INSERT INTO users (email, password_hash, is_verified) VALUES (%s, %s, %s)",
                    (email, generate_password_hash(password), True)
                )
                self._db.commit()
            return self._client.post('/login', data={
                'email': email, 'password': password
            }, follow_redirects=False)

    return AuthActions(client, db)


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
