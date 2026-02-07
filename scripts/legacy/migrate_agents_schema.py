from app import app
from database import get_db

def migrate():
    with app.app_context():
        print("Connecting to database...")
        db = get_db()
        
        # Check if logo_filename exists
        print("Checking schema...")
        cursor = db.execute("SELECT column_name FROM information_schema.columns WHERE table_name='agents' AND column_name='logo_filename'")
        if not cursor.fetchone():
            print("Adding 'logo_filename' column to 'agents' table...")
            db.execute("ALTER TABLE agents ADD COLUMN logo_filename TEXT")
            db.commit()
            print("Migration successful: Added logo_filename.")
        else:
            print("Schema is up to date: 'logo_filename' already exists.")

if __name__ == "__main__":
    migrate()
