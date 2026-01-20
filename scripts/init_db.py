import os
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from urllib.parse import urlparse

# Load .env manually if not loaded (or rely on parent shell)
# But simplified approach: just rely on DATABASE_URL
import sys
from dotenv import load_dotenv
load_dotenv()
# sys.path hack removed
# from config import Config - Removed to avoid triggering validation

def init_db():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL not set")
        return

    # Parse URL
    # format: postgresql://user:pass@host:port/dbname
    # We want to connect to 'postgres' db to create 'dbname'
    
    # Simple string manipulation or urlparse
    result = urlparse(db_url)
    username = result.username
    password = result.password
    hostname = result.hostname
    port = result.port
    dbname = result.path.lstrip('/')
    
    print(f"Target DB: {dbname}")
    
    # Connect to default 'postgres' database
    try:
        conn = psycopg2.connect(
            dbname='postgres',
            user=username,
            password=password,
            host=hostname,
            port=port
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()
        
        # Check if exists
        cursor.execute(f"SELECT 1 FROM pg_catalog.pg_database WHERE datname = '{dbname}'")
        exists = cursor.fetchone()
        
        if not exists:
            print(f"Creating database {dbname}...")
            cursor.execute(f"CREATE DATABASE {dbname}")
            print("Database created successfully.")
        else:
            print(f"Database {dbname} already exists.")
            
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"Error creating database: {e}")

if __name__ == "__main__":
    init_db()
