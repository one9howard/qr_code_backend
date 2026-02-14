#!/usr/bin/env python3
"""Fail-fast check that core application tables exist before boot."""

import os
import sys
from pathlib import Path

import psycopg2

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from utils.redaction import redact_database_url


REQUIRED_TABLES = (
    "users",
    "agents",
    "properties",
    "orders",
    "sign_assets",
)


def main() -> int:
    db_url = os.environ.get("DATABASE_URL", "").strip()
    if not db_url:
        print("[SchemaCheck] ERROR: DATABASE_URL is not set.")
        return 1

    try:
        conn = psycopg2.connect(db_url)
    except Exception as exc:
        print(f"[SchemaCheck] ERROR: Could not connect to {redact_database_url(db_url)}: {type(exc).__name__}")
        return 1

    missing = []
    try:
        with conn, conn.cursor() as cur:
            for table in REQUIRED_TABLES:
                cur.execute("SELECT to_regclass(%s)", (f"public.{table}",))
                if cur.fetchone()[0] is None:
                    missing.append(table)
    except Exception as exc:
        print(f"[SchemaCheck] ERROR: Failed while checking schema: {exc}")
        conn.close()
        return 1
    finally:
        conn.close()

    if missing:
        print(
            "[SchemaCheck] ERROR: Missing required table(s): "
            + ", ".join(missing)
            + ". Run migrations before starting the app."
        )
        return 1

    print("[SchemaCheck] Core schema check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
