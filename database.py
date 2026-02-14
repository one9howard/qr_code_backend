import os
import psycopg2
from psycopg2.extras import DictCursor
from flask import g, current_app
from utils.redaction import redact_database_url

def get_db():
    if 'db' not in g:
        db_url = os.environ.get("DATABASE_URL")
        if not db_url:
            raise RuntimeError("DATABASE_URL is required for Postgres connection.")

        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)

        if not db_url.startswith("postgresql://"):
            redacted = redact_database_url(db_url)
            raise ValueError(
                "Only Postgres is supported. DATABASE_URL must start with postgresql:// "
                f"(got {redacted})."
            )

        try:
            conn = psycopg2.connect(db_url, cursor_factory=DictCursor)
            g.db = PostgresDB(conn)
        except Exception as e:
            logger.error(
                "[DB] Connection Failed (%s) while connecting to %s",
                type(e).__name__,
                redact_database_url(db_url),
            )
            raise
    return g.db

def close_connection(exception=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()

import logging
from config import IS_PRODUCTION

logger = logging.getLogger(__name__)

class PostgresDB:
    """
    Strict Postgres wrapper.
    Passes SQL through to psycopg2 without modification.
    Expects %s placeholders.
    """
    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=None):
        cur = self._conn.cursor()
        try:
             cur.execute(sql, params)
             return cur
        except Exception as e:
             # Provide better context for debugging
             # In PROD, do NOT log raw SQL (PII Risk)
             logger.error(f"[DB] Query Failed: {e}")
             if not IS_PRODUCTION:
                 logger.error(f"[DB] SQL: {sql}")
             raise e

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    def cursor(self):
        return self._conn.cursor()
    
    # Intentionally omitted: lastrowid (Use RETURNING id + fetchone)
    # Intentionally omitted: total_changes (Use explicit commit)

# Missing Helpers from Refactor Restoration
def create_agent_snapshot(order_id, name, brokerage, email, phone, photo_filename, logo_filename=None):
    """
    Creates an immutable snapshot of agent details at the time of order.
    """
    db = get_db()
    db.execute(
        """
        INSERT INTO agent_snapshots (order_id, name, brokerage, email, phone, photo_filename, logo_filename)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (order_id, name, brokerage, email, phone, photo_filename, logo_filename)
    )

def get_agent_data_for_order(order_id):
    """
    Retrieves agent data for a specific order.
    Prioritizes the snapshot if it exists (historical accuracy).
    Falls back to the current agent profile if no snapshot exists (legacy orders).
    """
    db = get_db()
    
    # 1. Try Snapshot
    snapshot = db.execute(
        "SELECT * FROM agent_snapshots WHERE order_id = %s", 
        (order_id,)
    ).fetchone()
    
    if snapshot:
        # Return as dict-like object
        return snapshot
        
    # 2. Fallback to Current Profile via Property -> Agent
    # Note: Requires joining through properties to find the agent who OWNS the listing
    fallback = db.execute(
        """
        SELECT a.* 
        FROM agents a
        JOIN properties p ON p.agent_id = a.id
        JOIN orders o ON o.property_id = p.id
        WHERE o.id = %s
        """, 
        (order_id,)
    ).fetchone()
    
    return fallback
