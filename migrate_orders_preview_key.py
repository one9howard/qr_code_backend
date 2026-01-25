from app import app
from database import get_db

def migrate():
    with app.app_context():
        print("Connecting to database...")
        db = get_db()
        
        # Check if preview_key exists
        print("Checking schema...")
        cursor = db.execute("SELECT column_name FROM information_schema.columns WHERE table_name='orders' AND column_name='preview_key'")
        if not cursor.fetchone():
            print("Adding 'preview_key' column to 'orders' table...")
            db.execute("ALTER TABLE orders ADD COLUMN preview_key TEXT")
            db.commit()
            print("Migration successful: Added preview_key.")
        else:
            print("Schema is up to date: 'preview_key' already exists.")

if __name__ == "__main__":
    migrate()
