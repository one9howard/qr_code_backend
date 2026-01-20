
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def test_fk():
    db_url = os.environ.get("DATABASE_URL")
    print(f"Connecting to: {db_url}")
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
