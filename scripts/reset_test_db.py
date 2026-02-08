#!/usr/bin/env python3
"""
Deterministic test database reset.

Behavior:
- Default DB name: insite_test (configurable via TEST_DB_NAME env var)
- Connects to admin DB (postgres) and drop/create the test DB
- Robust regardless of what DATABASE_URL points to
"""
import psycopg2
import os
from urllib.parse import urlparse

# Canonical test DB name
TEST_DB_NAME = os.getenv("TEST_DB_NAME", "insite_test")

# Get connection string
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/insite_test")


def reset_test_db():
    """Drop and recreate the test database."""
    parsed = urlparse(DATABASE_URL)
    
    # Extract connection info (we'll connect to 'postgres' admin DB)
    conn_params = {
        'dbname': 'postgres',  # Always connect to admin DB
        'user': parsed.username or 'postgres',
        'password': parsed.password or 'postgres',
        'host': parsed.hostname or 'localhost',
        'port': parsed.port or 5432,
    }
    
    print(f"[reset_test_db] Connecting to {conn_params['host']}:{conn_params['port']} as {conn_params['user']}")
    print(f"[reset_test_db] Target test database: {TEST_DB_NAME}")
    
    conn = psycopg2.connect(**conn_params)
    conn.autocommit = True
    cur = conn.cursor()
    
    # Terminate existing connections to the test DB
    print(f"[reset_test_db] Terminating connections to {TEST_DB_NAME}...")
    cur.execute(
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s",
        (TEST_DB_NAME,)
    )
    
    # Drop the test database
    print(f"[reset_test_db] Dropping {TEST_DB_NAME}...")
    cur.execute(f"DROP DATABASE IF EXISTS {TEST_DB_NAME}")
    
    # Create the test database
    print(f"[reset_test_db] Creating {TEST_DB_NAME}...")
    cur.execute(f"CREATE DATABASE {TEST_DB_NAME}")
    
    cur.close()
    conn.close()
    print("[reset_test_db] Done.")


if __name__ == "__main__":
    reset_test_db()
