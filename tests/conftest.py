import os
import tempfile
import subprocess
import sys

# Load .env explicitly for tests (since we aren't starting via Flask CLI)
from dotenv import load_dotenv
load_dotenv()


# IMPORTANT: Set env vars BEFORE importing the app/config modules.
# config.py evaluates env at import time.
_INSTANCE_DIR = os.environ.get("INSTANCE_DIR")
if not _INSTANCE_DIR:
    _INSTANCE_DIR = os.path.join(tempfile.gettempdir(), "insite_test_instance")
    os.environ["INSTANCE_DIR"] = _INSTANCE_DIR

os.environ.setdefault("FLASK_ENV", "test")
os.environ.setdefault("APP_STAGE", "test")
os.environ.setdefault("BASE_URL", "http://localhost")
os.environ["SECRET_KEY"] = "test-secret"
os.environ["PRINT_JOBS_TOKEN"] = "test-print-token"

def _force_env_if_blank(key: str, value: str):
    v = os.environ.get(key)
    if v is None or not str(v).strip():
        os.environ[key] = value

# Robustly set test secrets (overriding empty/poisoned .env values)
_force_env_if_blank("STRIPE_SECRET_KEY", "sk_test_dummy")
_force_env_if_blank("STRIPE_WEBHOOK_SECRET", "whsec_dummy")
_force_env_if_blank("STRIPE_PUBLISHABLE_KEY", "pk_test_dummy")  # harmless if unused


# Fix DATABASE_URL for local test execution (Windows Host -> Docker Service mismatch)
_db_url = os.environ.get("DATABASE_URL")
if _db_url and "@db:" in _db_url:
    # We are likely running on host, but config points to docker 'db' service.
    # Swap to localhost (assuming port 5432 is exposed) AND use DSN format for Windows compatibility
    # Using replace ensures we keep credentials from .env
    # Patch DATABASE_URL to use localhost when running tests on host machine (outside Docker network)
    val = _db_url.replace("@db:", "@localhost:")
    os.environ["DATABASE_URL"] = val


# SAFETY GUARD: Prevent accidental test runs against remote/production DBs
def _check_test_db_safety():
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        return
        
    try:
        from urllib.parse import urlparse
        parsed = urlparse(db_url)
        hostname = parsed.hostname or ""
        
        # Strict Allow List: localhost only (Docker 'db' alias should have been patched above)
        is_local = hostname.lower() in ("localhost", "127.0.0.1")
        
        if not is_local and os.environ.get("ALLOW_REMOTE_TEST_DB") != "1":
            print(f"!!! CRITICAL TEST SAFETY ERROR !!!")
            # Don't print full URL to avoid leaking secrets
            print(f"DATABASE_URL points to remote host: '{hostname}'")
            print("Tests are blocked to prevent data loss.")
            print("To override, set ALLOW_REMOTE_TEST_DB=1")
            print("Otherwise, use: postgresql://postgres:postgres@localhost:5432/insite_test")
            sys.exit(1)
            
    except Exception as e:
        print(f"Error checking DATABASE_URL safety: {e}")
        sys.exit(1)

_check_test_db_safety()



import pytest


@pytest.fixture(scope="session", autouse=True)
def _migrate_db_once():
    """Run Alembic migrations once per test session."""
    db_url = os.environ.get("DATABASE_URL", "")
    
    if not db_url or not db_url.startswith("postgres"):
        safe_msg = "EMPTY"
        if db_url:
            try:
                from urllib.parse import urlparse
                p = urlparse(db_url)
                safe_msg = f"{p.scheme}://{p.hostname}"
            except Exception:
                safe_msg = "INVALID_URL"

        raise RuntimeError(
            "CRITICAL: Tests must run against Postgres (DATABASE_URL=postgresql://...). Non-Postgres DBs are strictly forbidden.\n"
            f"Current URL: {safe_msg}"
        )

    # Run migrations using the project's migrate.py so it's consistent with prod.
    subprocess.check_call([sys.executable, "migrate.py"], cwd=os.path.dirname(__file__) + "/..")
    yield


@pytest.fixture()
def app():
    from app import create_app
    a = create_app({
        "TESTING": True,
        "SERVER_NAME": "localhost",
        "WTF_CSRF_ENABLED": False,
        "SESSION_COOKIE_SECURE": False,
        "REMEMBER_COOKIE_SECURE": False,
    })
    return a


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def db(app):
    from database import get_db

    with app.app_context():
        d = get_db()

        # Truncate all app tables between tests
        tables = d.execute(
            """SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename != 'alembic_version'"""
        ).fetchall()
        table_names = [row["tablename"] for row in tables]
        if table_names:
            stmt = "TRUNCATE TABLE " + ", ".join([f'"{t}"' for t in table_names]) + " RESTART IDENTITY CASCADE"
            d.execute(stmt)
            d.commit()

        yield d
