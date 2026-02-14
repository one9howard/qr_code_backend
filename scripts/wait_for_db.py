#!/usr/bin/env python3
"""Wait for Postgres to be reachable.

Used by Docker entrypoint scripts before running Alembic migrations.

This checks real DB readiness (credentials + accept loop), not just TCP.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import psycopg2

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from utils.redaction import redact_database_url

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
            safe_url = redact_database_url(database_url)
            if elapsed >= timeout_seconds:
                print(
                    f"[wait_for_db] TIMEOUT after {timeout_seconds}s while connecting to {safe_url}: "
                    f"{type(e).__name__}"
                )
                raise
            print(
                f"[wait_for_db] Not ready yet ({elapsed:.1f}s) for {safe_url}: "
                f"{type(e).__name__}"
            )
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
    print(f"[wait_for_db] Waiting for Postgres: {redact_database_url(database_url)}")
    try:
        wait_for_db(database_url, timeout_seconds=timeout)
        return 0
    except Exception:
        return 1


if __name__ == "__main__":
    sys.exit(main())
