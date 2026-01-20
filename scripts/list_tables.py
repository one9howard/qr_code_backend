
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def list_tables():
    db_url = os.environ.get("DATABASE_URL")
    print(f"Connecting to: {db_url}")
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
