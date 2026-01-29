
import os
import sys
from flask import Flask
from config import INSTANCE_DIR
from database import get_db

app = Flask(__name__)
app.config['INSTANCE_DIR'] = INSTANCE_DIR

def check_keys():
    import os
    # Override for host machine connection
    os.environ['DATABASE_URL'] = 'postgresql://postgres:postgres@localhost:5432/qrapp'
    with app.app_context():
        db = get_db()
        print("--- Checking Property Photos ---")
        rows = db.execute("SELECT id, property_id, filename FROM property_photos LIMIT 5").fetchall()
        for r in rows:
            print(f"ID: {r['id']}, PropID: {r['property_id']}, Filename: '{r['filename']}'")

        print("\n--- Checking Agent Photos ---")
        rows = db.execute("SELECT id, photo_filename, logo_filename FROM agents WHERE photo_filename IS NOT NULL LIMIT 5").fetchall()
        for r in rows:
            print(f"ID: {r['id']}, Photo: '{r['photo_filename']}', Logo: '{r['logo_filename']}'")

if __name__ == "__main__":
    check_keys()
