import sys
import os
import sqlalchemy
from sqlalchemy import create_engine, text

# Add parent dir to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import DB_PATH

def migrate_photos():
    database_url = os.environ.get("DATABASE_URL")
    
    # Handle Railway's postgres://
    if database_url and database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
        
    if not database_url:
        print(f"No DATABASE_URL found. Using local DB_PATH: {DB_PATH}")
        if not os.path.exists(DB_PATH):
            print("Local database file not found.")
            return
        database_url = f"sqlite:///{DB_PATH}"
    
    print(f"Connecting to database...")
    engine = create_engine(database_url)
    
    with engine.begin() as conn:
        # 1. Property Photos
        print("Checking Property Photos...")
        result = conn.execute(text("SELECT id, filename FROM property_photos"))
        
        # Determine how to clear absolute paths based on OS style separators
        # We look for typical absolute path indicators
        
        count = 0
        for row in result.fetchall():
            # SQLAlchemy rows access by index or key
            try:
                p_id = row.id
                old_val = row.filename
            except AttributeError:
                # Fallback for some older SA versions or return types
                p_id = row[0]
                old_val = row[1]
                
            if not old_val: continue
            
            # Check if absolute path (Windows C:\ or Unix /)
            # We want to catch things like "C:\Users\..." or "/var/www/..."
            is_likely_abs = os.path.isabs(old_val) or ":\\" in old_val or old_val.startswith("/")
            
            if is_likely_abs:
                basename = os.path.basename(old_val)
                new_key = f"uploads/properties/{basename}"
                
                conn.execute(
                    text("UPDATE property_photos SET filename = :new_key WHERE id = :id"),
                    {"new_key": new_key, "id": p_id}
                )
                print(f"  Fixed Property Photo {p_id}: {basename} -> {new_key}")
                count += 1
                
        print(f"  Updated {count} property photos.")

        # 2. Agent Photos
        print("Checking Agent Photos...")
        result = conn.execute(text("SELECT id, photo_filename FROM agents"))
        
        count = 0
        for row in result.fetchall():
            try:
                a_id = row.id
                old_val = row.photo_filename
            except AttributeError:
                a_id = row[0]
                old_val = row[1]
                
            if not old_val: continue
            
            is_likely_abs = os.path.isabs(old_val) or ":\\" in old_val or old_val.startswith("/")
            
            if is_likely_abs:
                basename = os.path.basename(old_val)
                new_key = f"uploads/agents/{basename}"
                
                conn.execute(
                    text("UPDATE agents SET photo_filename = :new_key WHERE id = :id"),
                    {"new_key": new_key, "id": a_id}
                )
                print(f"  Fixed Agent {a_id}: {basename} -> {new_key}")
                count += 1

        print(f"  Updated {count} agents.")

    print("Done.")

if __name__ == "__main__":
    migrate_photos()
