
import os
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

def recreate_db():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL not set")
        return

    # Parse to connect to postgres db
    try:
        # Standard URL parsing
        result = urlparse(db_url)
        username = result.username
        password = result.password
        hostname = result.hostname
        port = result.port
        dbname = result.path.lstrip('/')
        
        print(f"Recreating DB: {dbname}")
        
        conn = psycopg2.connect(
            dbname='postgres',
            user=username,
            password=password,
            host=hostname,
            port=port
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cur = conn.cursor()
        
        # Terminate connections
        cur.execute(f"""
            SELECT pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE datname = '{dbname}' AND pid <> pg_backend_pid()
        """)
        
        # Drop
        print(f"Dropping {dbname}...")
        cur.execute(f"DROP DATABASE IF EXISTS {dbname}")
        
        # Create
        print(f"Creating {dbname}...")
        cur.execute(f"CREATE DATABASE {dbname}")
        
        print("Done.")
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    recreate_db()
