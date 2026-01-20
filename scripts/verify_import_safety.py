import os
import sys

# Ensure we can import app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Set a fake DB path that definitely doesn't exist
fake_db = "should_not_exist.db"
os.environ["DB_PATH"] = fake_db
os.environ["INSTANCE_DIR"] = "." 
# Ensure checking strict config doesn't kill us if we are "in production" implicitly, 
# acting as dev here for the import test.
os.environ["FLASK_ENV"] = "development" 

if os.path.exists(fake_db):
    os.remove(fake_db)

print("Importing app...")
from app import app

if os.path.exists(fake_db):
    print("FAILURE: Importing app created the database file! Migrations ran implicitly.")
    sys.exit(1)
else:
    print("SUCCESS: Importing app did NOT create the database file.")
    sys.exit(0)
