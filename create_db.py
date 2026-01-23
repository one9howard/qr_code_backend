import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
import os

# Use the credentials from .env or defaults
DB_HOST = "localhost"
DB_USER = "postgres"
DB_PASS = "postgres"
DB_PORT = "5432"

def create_database():
    try:
        # Connect to 'postgres' db to create new db
        conn = psycopg2.connect(
            dbname="postgres",
            user=DB_USER,
            password=DB_PASS,
            host=DB_HOST,
            port=DB_PORT
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cur = conn.cursor()
        
        # Check if exists
        cur.execute("SELECT 1 FROM pg_catalog.pg_database WHERE datname = 'insitesigns'")
        exists = cur.fetchone()
        
        if not exists:
            cur.execute("CREATE DATABASE insitesigns")
            print("Database 'insitesigns' created successfully.")
        else:
            print("Database 'insitesigns' already exists.")
            
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Error creating database: {e}")

if __name__ == "__main__":
    create_database()
