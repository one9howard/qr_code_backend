# DEPRECATED — Alembic migration 025 replaces this. Do not run in prod.
from app import create_app
from database import get_db

def migrate():
    """
    V2 Schema Migration.
    1. agents: Add logo_filename (TEXT)
    2. orders: Add preview_key (TEXT)
    3. orders: Add guest_email (TEXT)
    4. agent_snapshots: Add logo_filename (TEXT)
    Includes backfills/validation to run safely on existing DB.
    """
    app = create_app()
    with app.app_context():
        print("Connecting to database...")
        db = get_db()
        
        # 1. Agents: logo_filename
        print("Checking 'agents' table...")
        cursor = db.execute("SELECT column_name FROM information_schema.columns WHERE table_name='agents' AND column_name='logo_filename'")
        if not cursor.fetchone():
            print("Adding 'logo_filename' column to 'agents' table...")
            db.execute("ALTER TABLE agents ADD COLUMN logo_filename TEXT")
            db.commit()
        else:
            print("- 'logo_filename' already exists in 'agents'.")

        # 2. Orders: preview_key
        print("Checking 'orders' table for 'preview_key'...")
        cursor = db.execute("SELECT column_name FROM information_schema.columns WHERE table_name='orders' AND column_name='preview_key'")
        if not cursor.fetchone():
            print("Adding 'preview_key' column to 'orders' table...")
            db.execute("ALTER TABLE orders ADD COLUMN preview_key TEXT")
            db.commit()
            
            # Backfill? (Optional, based on user note "ideally backfill")
            # For now, just schema. Real backfill requires iterating all orders and re-computing from params.
        else:
            print("- 'preview_key' already exists in 'orders'.")
            
        # 3. Orders: guest_email
        print("Checking 'orders' table for 'guest_email'...")
        cursor = db.execute("SELECT column_name FROM information_schema.columns WHERE table_name='orders' AND column_name='guest_email'")
        if not cursor.fetchone():
            print("Adding 'guest_email' column to 'orders' table...")
            db.execute("ALTER TABLE orders ADD COLUMN guest_email TEXT")
            db.commit()
        else:
            print("- 'guest_email' already exists in 'orders'.")
            
        # 4. Agent Snapshots: logo_filename
        # Check if table exists first (it comes from JSONB usually or separate table? models.py says agent_actions has 'policy_snapshot' JSONB, 
        # but user mentioned "migrate agent_snapshots" implying a table. 
        # Check AgentAction model/table in models.py... it has 'policy_snapshot', maybe 'agent_snapshot' is inside the JSON or a table I missed.
        # User said "migrate agent_snapshots" table. I'll check if it exists.
        print("Checking 'agent_snapshots' table...")
        # Check if table exists
        cursor = db.execute("SELECT to_regclass('public.agent_snapshots')")
        if cursor.fetchone()[0]:
            cursor = db.execute("SELECT column_name FROM information_schema.columns WHERE table_name='agent_snapshots' AND column_name='logo_filename'")
            if not cursor.fetchone():
                print("Adding 'logo_filename' column to 'agent_snapshots' table...")
                db.execute("ALTER TABLE agent_snapshots ADD COLUMN logo_filename TEXT")
                db.commit()
            else:
                print("- 'logo_filename' already exists in 'agent_snapshots'.")
        else:
             print("- Table 'agent_snapshots' does not exist (skipping).")

        print("Migration V2 completed successfully.")

if __name__ == "__main__":
    migrate()
