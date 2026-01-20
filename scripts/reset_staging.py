"""
Reset Staging Database Script

Use this script to wipe USER data from the database while keeping schema intact.
It deletes data from:
- orders
- print_jobs
- property_views
- qr_scans
- leads
- properties
- agents
- users

WARNING: This deletes ALL user data. Do not run in production unless you intend to wipe everything.

Usage:
    export DATABASE_URL=postgresql://...
    export STORAGE_BACKEND=s3  # (Optional, if you want to wipe S3 too - requires AWS creds)
    python scripts/reset_staging.py
"""

import sys
import os

# Add parent dir to path to import app context
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from database import get_db

def reset_db():
    app = create_app()
    with app.app_context():
        db = get_db()
        db_url = app.config.get('DATABASE_URL')
        
        if not db_url:
            # Fallback check os.environ directly
            db_url = os.environ.get("DATABASE_URL")
            
        print(f"Database Config Found: {'Yes' if db_url else 'No'}")
        
        if not db_url:
            print("ERROR: DATABASE_URL not found in app config or environment.")
            print("Debug Info:")
            print(f"  FLASK_ENV: {os.environ.get('FLASK_ENV')}")
            print(f"  APP_STAGE: {os.environ.get('APP_STAGE')}")
            # List keys starting with DATA or POSTGRES
            keys = [k for k in os.environ.keys() if 'DATA' in k or 'POSTGRES' in k or 'URL' in k]
            print(f"  Related Env Keys: {keys}")
            return

        print("⚠ WARNING: This will delete ALL data from the configured database.")
        print(f"Database: {db_url}")
        confirm = input("Are you sure? Type 'DELETE' to confirm: ")
        
        if confirm != "DELETE":
            print("Aborted.")
            return

        print("Deleting data...")
        # Order matters due to foreign keys (delete children first)
        tables = [
            "print_jobs",
            "order_agent_snapshot",
            "orders", 
            "property_views",
            "qr_scans",
            "leads",
            "property_photos",
            "properties",
            "agents",
            "users",
            #"stripe_customers",
            "stripe_events"
        ]
        
        for table in tables:
            try:
                # Use TRUNCATE CASCADE since we are on Postgres
                if "postgresql" in db_url:
                    print(f"  Truncating {table}...")
                    db.execute(f"TRUNCATE TABLE {table} CASCADE")
                else:
                    # Should not happen per new config rules, but fallback to delete
                    print(f"  Deleting from {table}...")
                    db.execute(f"DELETE FROM {table}")
            except Exception as e:
                db.rollback() 
                print(f"  Error clearing {table}: {e}")
                # Fallback to DELETE if TRUNCATE fails
                try:
                    db.execute(f"DELETE FROM {table}")
                except Exception as e2:
                    db.rollback()
                    print(f"  Fallback delete failed: {e2}")

        db.commit()
        print("✔ Database wiped successfully.")

if __name__ == "__main__":
    reset_db()
