
import psycopg2
import os
from urllib.parse import urlparse

# Force test DB URL for this script if not explicit
url = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/insite_test")

def reset_test_db():
    print(f"Resetting DB: {url}")
    parsed = urlparse(url)
    dbname = parsed.path.lstrip('/')
    
    # Connect to 'postgres' to drop/create
    conn = psycopg2.connect(
        dbname='postgres',
        user=parsed.username,
        password=parsed.password,
        host=parsed.hostname,
        port=parsed.port
    )
    conn.autocommit = True
    cur = conn.cursor()
    
    # Terminate connections
    cur.execute(f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{dbname}'")
    
    # Drop
    print(f"Dropping {dbname}...")
    cur.execute(f"DROP DATABASE IF EXISTS {dbname}")
    
    # Create
    print(f"Creating {dbname}...")
    cur.execute(f"CREATE DATABASE {dbname}")
    
    cur.close()
    conn.close()
    print("Done.")

if __name__ == "__main__":
    reset_test_db()
