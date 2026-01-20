
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def check_users_cols():
    db_url = os.environ.get("DATABASE_URL")
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    
    cur.execute("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'users'
    """)
    
    rows = cur.fetchall()
    print("Users columns:")
    for row in rows:
        print(f"- {row[0]} ({row[1]})")
        
    conn.close()

if __name__ == "__main__":
    check_users_cols()
