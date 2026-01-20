#!/usr/bin/env python3
"""Wait for Postgres to be reachable.

Used by Docker entrypoint scripts before running Alembic migrations.

This checks real DB readiness (credentials + accept loop), not just TCP.
"""

from __future__ import annotations

import os
import sys
import time
from urllib.parse import urlparse

import psycopg2


def _mask_database_url(url: str) -> str:
    """Mask password for logs."""
    try:
        p = urlparse(url)
        if p.username:
            user = p.username
        else:
            user = ""

        host = p.hostname or ""
        port = p.port or ""
        db = (p.path or "").lstrip("/")
        scheme = p.scheme or "postgresql"
        if user:
            return f"{scheme}://{user}:****@{host}:{port}/{db}"
        return f"{scheme}://{host}:{port}/{db}"
    except Exception:
        return "<unparseable DATABASE_URL>"


def wait_for_db(database_url: str, timeout_seconds: int = 60, sleep_seconds: float = 1.0) -> None:
    """Exit 0 when DB is ready; exit 1 on timeout."""
    start = time.time()

    # Ensure a short connection timeout per attempt.
    connect_kwargs = {
        "connect_timeout": 3,
        "sslmode": os.environ.get("PGSSLMODE", "prefer"),
    }

    while True:
        try:
            conn = psycopg2.connect(database_url, **connect_kwargs)
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.fetchone()
            cur.close()
            conn.close()
            print("[wait_for_db] Postgres is ready")
            return
        except Exception as e:
            elapsed = time.time() - start
            if elapsed >= timeout_seconds:
                print(f"[wait_for_db] TIMEOUT after {timeout_seconds}s: {e}")
                raise
            print(f"[wait_for_db] Not ready yet ({elapsed:.1f}s): {e}")
            time.sleep(sleep_seconds)


def main() -> int:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        print("[wait_for_db] DATABASE_URL is not set")
        return 1
    
    # Handle postgres:// -> postgresql:// for SQLAlchemy/psycopg2 consistency
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    timeout = int(os.environ.get("DB_WAIT_TIMEOUT", "60"))
    print(f"[wait_for_db] Waiting for Postgres: {_mask_database_url(database_url)}")
    try:
        wait_for_db(database_url, timeout_seconds=timeout)
        return 0
    except Exception:
        return 1


if __name__ == "__main__":
    sys.exit(main())
