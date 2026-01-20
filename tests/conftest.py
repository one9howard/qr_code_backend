import os
import tempfile
import subprocess
import sys


# Load .env explicitly for tests (since we aren't starting via Flask CLI)
from dotenv import load_dotenv
load_dotenv()
print(f"DEBUG_CONFTEST_TOP: DATABASE_URL={os.environ.get('DATABASE_URL')}")

# IMPORTANT: Set env vars BEFORE importing the app/config modules.
# config.py evaluates env at import time.
_INSTANCE_DIR = os.environ.get("INSTANCE_DIR")
if not _INSTANCE_DIR:
    _INSTANCE_DIR = os.path.join(tempfile.gettempdir(), "insite_test_instance")
    os.environ["INSTANCE_DIR"] = _INSTANCE_DIR

os.environ.setdefault("FLASK_ENV", "test")
os.environ.setdefault("APP_STAGE", "test")
os.environ.setdefault("BASE_URL", "http://localhost")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("PRINT_SERVER_TOKEN", "test-print-token")
os.environ.setdefault("STRIPE_SECRET_KEY", "sk_test_dummy")
os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "whsec_dummy")
os.environ.setdefault("STORAGE_BACKEND", "local")

# Fix DATABASE_URL for local test execution (Windows Host -> Docker Service mismatch)
_db_url = os.environ.get("DATABASE_URL")
if _db_url and "@db:" in _db_url:
    # We are likely running on host, but config points to docker 'db' service.
    # Swap to localhost (assuming port 5432 is exposed) AND use DSN format for Windows compatibility
    # Using replace ensures we keep credentials from .env
    # Patch DATABASE_URL to use localhost when running tests on host machine (outside Docker network)
    val = _db_url.replace("@db:", "@localhost:")
    os.environ["DATABASE_URL"] = val


import pytest


@pytest.fixture(scope="session", autouse=True)
def _migrate_db_once():
    """Run Alembic migrations once per test session."""
    db_url = os.environ.get("DATABASE_URL", "")
    
    if not db_url:
        raise RuntimeError(
            "DATABASE_URL must be set for tests (Postgres required).\n"
            "Run: docker run --name qrapp-db -e POSTGRES_PASSWORD=postgres -p 5432:5432 -d postgres\n"
            "Then: export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/qrapp"
        )

    if db_url.startswith("sqlite"):
        raise ValueError(
            f"SQLite URL detected: {db_url}. SQLite is NOT supported for tests.\n"
            "Please unset DATABASE_URL or set it to a valid Postgres equivalent.\n"
            "Example: postgresql://postgres:postgres@localhost:5432/qrapp"
        )

    # Run migrations using the project's migrate.py so it's consistent with prod.
    try:
        subprocess.check_call([sys.executable, "migrate.py"], cwd=os.path.dirname(__file__) + "/..")
    except subprocess.CalledProcessError as e:
        # Fallback: Print error but continue if possible (testing on existing db?)
        print(f"WARNING: Migration failed during test setup: {e}")
        # We assume manual migration might have been done.
        pass
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
    # Patch the imported constant in printing blueprint to match test env
    import routes.printing
    routes.printing.PRINT_SERVER_TOKEN = os.environ["PRINT_SERVER_TOKEN"]

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
