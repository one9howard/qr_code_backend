#!/usr/bin/env python3
import sys
import os
from dotenv import load_dotenv

# Load .env before reading any environment variables
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    load_dotenv()
    print("[Manage] Loaded .env file")

# Put this script in the root so it can import local modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def migrate():
    print("[Manage] Starting database migration...")

    # logic: If DATABASE_URL exists, run Alembic directly (no Flask app).
    # This ensures one-off migration tasks don't crash due to missing app secrets.
    database_url = os.environ.get("DATABASE_URL", "").strip()

    # Railway uses postgres:// but SQLAlchemy 1.4+ requires postgresql://
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
        print("[Manage] Converted postgres:// to postgresql://")
        # CRITICAL: Update os.environ so Alembic env.py sees the corrected URL
        os.environ["DATABASE_URL"] = database_url
    
    # Debug: show URL format (mask password)
    if database_url:
        try:
            # Mask password for logging
            from urllib.parse import urlparse
            parsed = urlparse(database_url)
            masked = f"{parsed.scheme}://{parsed.username}:****@{parsed.hostname}:{parsed.port}/{parsed.path.lstrip('/')}"
            print(f"[Manage] DATABASE_URL format: {masked}")
        except Exception as e:
            print(f"[Manage] Could not parse URL for logging: {e}")
            print(f"[Manage] DATABASE_URL starts with: {database_url[:30]}...")

    if not database_url:
        print("[Manage] ERROR: DATABASE_URL environment variable is not set.")
        print("[Manage] Only Postgres is supported.")
        sys.exit(1)

    if not database_url.startswith("postgres"):
        try:
            from urllib.parse import urlparse
            p = urlparse(database_url)
            safe_msg = f"{p.scheme}://{p.hostname}"
        except Exception:
            safe_msg = "invalid_url"
        print(f"[Manage] ERROR: Only Postgres is supported (got {safe_msg})")
        sys.exit(1)

    try:
        parsed = urlparse(database_url)
        if parsed.hostname == 'db':
            try:
                import socket
                socket.gethostbyname("db")
            except Exception:
                print("[Manage] ERROR: DATABASE_URL host is 'db' which only resolves inside docker-compose. Either run migrations inside docker-compose or change host to localhost.")
                sys.exit(1)
    except ImportError:
        pass  # Basic robust fallback if imports fail, though stdlib usually safe

    print("[Manage] Detected DATABASE_URL, using Alembic for Postgres...")
    try:
        from alembic.config import Config
        from alembic import command

        # Ensure we are in the right directory for alembic.ini
        alembic_cfg = Config("alembic.ini")
        command.upgrade(alembic_cfg, "head")
        print("[Manage] Alembic migration to 'head' successful.")
    except Exception as e:
        print(f"[Manage] Alembic migration FAILED: {e}")
        sys.exit(1)

    print("[Manage] Database migration completed successfully.")

if __name__ == "__main__":
    migrate()
