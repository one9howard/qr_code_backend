import psycopg2
import sys

# DATABASE_URL from .env
DB_URL = "postgresql://postgres:postgres@127.0.0.1:5432/insite"

try:
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    # "user" is a reserved word in Postgres, so quote it
    cur.execute('SELECT verification_code FROM users WHERE email = %s', ('audit_round4_v2@example.com',))
    row = cur.fetchone()
    if row:
        print(f"VERIFICATION_CODE:{row[0]}")
    else:
        print("VERIFICATION_CODE:NOT_FOUND")
    conn.close()
except Exception as e:
    print(f"ERROR:{e}")
