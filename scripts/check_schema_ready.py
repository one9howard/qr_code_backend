#!/usr/bin/env python3
"""Fail-fast check that core application tables exist before boot."""

import os
import sys
from urllib.parse import urlparse

import psycopg2


REQUIRED_TABLES = (
    "users",
    "agents",
    "properties",
    "orders",
    "sign_assets",
)


def _masked_db_url(url: str) -> str:
    try:
        parsed = urlparse(url or "")
        if not parsed.scheme:
            return "EMPTY"
        host = parsed.hostname or "unknown-host"
        port = f":{parsed.port}" if parsed.port else ""
        db = parsed.path.lstrip("/") or "unknown-db"
        return f"{parsed.scheme}://{host}{port}/{db}"
    except Exception:
        return "INVALID_URL"


def main() -> int:
    db_url = os.environ.get("DATABASE_URL", "").strip()
    if not db_url:
        print("[SchemaCheck] ERROR: DATABASE_URL is not set.")
        return 1

    try:
        conn = psycopg2.connect(db_url)
    except Exception as exc:
        print(f"[SchemaCheck] ERROR: Could not connect to {_masked_db_url(db_url)}: {exc}")
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
