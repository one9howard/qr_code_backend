# DEPRECATED — Alembic migration 025 replaces this. Do not run in prod.
from database import get_db

def ensure_agent_columns():
    """
    Checks for required columns in 'agents' table and adds them if missing.
    Specific for the 'Profile Assets' feature (logo_filename).
    """
    try:
        db = get_db()
        # Check logo_filename
        cursor = db.execute("SELECT column_name FROM information_schema.columns WHERE table_name='agents' AND column_name='logo_filename'")
        if not cursor.fetchone():
            import logging
            logging.getLogger(__name__).info("[Migration] Adding 'logo_filename' column to agents table...")
            db.execute("ALTER TABLE agents ADD COLUMN logo_filename TEXT")
            db.commit()
            logging.getLogger(__name__).info("[Migration] Done.")
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"[Migration] Warning: Schema check failed: {e}")
