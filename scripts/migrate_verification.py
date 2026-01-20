
import sys
import os

# Add parent dir to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from database import get_db, ensure_column

app = create_app()

with app.app_context():
    print("Migrating database for Email Verification...")
    db = get_db()
    ensure_column(db, 'users', 'verification_code', "TEXT")
    ensure_column(db, 'users', 'verification_code_expires_at', "TIMESTAMP")
    db.commit()
    print("Migration complete.")
