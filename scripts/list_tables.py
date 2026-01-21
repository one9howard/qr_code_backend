
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

def list_tables():
    db_url = os.environ.get("DATABASE_URL")
    print(f"Connecting to: {_mask_database_url(db_url)}")
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    
    cur.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public'
    """)
    
    rows = cur.fetchall()
    print("Tables found:")
    for row in rows:
        print(f"- {row[0]}")
        
    conn.close()

if __name__ == "__main__":
    list_tables()