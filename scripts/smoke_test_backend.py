import os
import sys
# Path hack
sys.path.append(os.getcwd())

from app import app
from database import get_db
from constants import SIGN_SIZES

# printing recognized sizes
print(f"DEBUG: SIGN_SIZES keys: {list(SIGN_SIZES.keys())}")

# Disable CSRF
app.config['WTF_CSRF_ENABLED'] = False
app.config['TESTING'] = True

with app.test_client() as client:
    print("Testing /submit with sign_size='24x36'...")
    # Using existing agent email to avoid unique constraint if agent exists, 
    # but since db is persistent, creating new property is safer.
    # Agent logic: if email exists, updates it. So reusing email is fine.
    
    resp = client.post('/submit', data={
        "address": "999 Debug Lane",
        "beds": "5",
        "baths": "4",
        "agent_name": "Debug Agent",
        "brokerage": "Debug Realty",
        "email": "debug_test_backend@example.com", 
        "phone": "555-9999",
        "sign_size": "24x36",
        "sign_color": "#1F6FEB"
    }, follow_redirects=True)
    
    print(f"Response Status: {resp.status_code}")
    if resp.status_code != 200:
        print(f"Error: {resp.data}")
    
    # Check DB
    with app.app_context():
        db = get_db()
        # Get the latest order created (likely ours)
        row = db.execute("SELECT sign_size, status FROM orders ORDER BY id DESC LIMIT 1").fetchone()
        if row:
            print(f"DB Result -> Sign Size: '{row['sign_size']}', Status: {row['status']}")
            if row['sign_size'] == '24x36':
                print("SUCCESS: Backend correctly saved 24x36.")
            else:
                print("FAILURE: Backend saved wrong size.")
        else:
            print("FAILURE: No order created.")
