
import os
import psycopg2
from dotenv import load_dotenv

def _mask_database_url(url: str) -> str:
    """Return a safely masked DB URL for logs (no credentials)."""
    try:
        from urllib.parse import urlparse
        p = urlparse(url or "")
        if not p.scheme:
            return "EMPTY"
        host = p.hostname or "UNKNOWN_HOST"
        port = p.port or ""
        return f"{p.scheme}://{host}{(':'+str(port)) if port else ''}"
    except Exception:
        return "INVALID_URL"
load_dotenv()

def test_fk():
    db_url = os.environ.get("DATABASE_URL")
    print(f"Connecting to: {_mask_database_url(db_url)}")
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    
    try:
        print("Attempting to create table with FK to users...")
        cur.execute("""
            CREATE TABLE test_fk_manual (
                id serial primary key, 
                user_id integer references users(id)
            )
        """)
        conn.commit()
        print("Success! Table created.")
        
        print("Dropping test table...")
        cur.execute("DROP TABLE test_fk_manual")
        conn.commit()
        print("Dropped.")
        
    except Exception as e:
        print(f"FAILED: {e}")
        conn.rollback()
        
    conn.close()

if __name__ == "__main__":
    test_fk()