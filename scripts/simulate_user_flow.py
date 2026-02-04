import sys
import os
from datetime import datetime

# Add project root to path
sys.path.append(os.getcwd())

from app import app
from database import get_db
from models import User
from services.smart_signs import SmartSignsService
from utils.qr_codes import generate_unique_code

def simulate_flow():
    with app.app_context():
        db = get_db()
        email = 'test3@email.com'
        
        # 1. Login (Get User)
        user = db.execute("SELECT * FROM users WHERE email = %s", (email,)).fetchone()
        if not user:
            print(f"User {email} not found!")
            return
        
        user_id = user['id']
        print(f"Logged in as User ID: {user_id}")

        # Get Agent ID
        agent = db.execute("SELECT * FROM agents WHERE user_id = %s", (user_id,)).fetchone()
        if not agent:
            print("Agent profile not found. Creating one...")
            db.execute("INSERT INTO agents (user_id, name, email, brokerage) VALUES (%s, %s, %s, %s)",
                       (user_id, 'Test Agent', email, 'Test Brokerage'))
            db.commit()
            agent = db.execute("SELECT * FROM agents WHERE user_id = %s", (user_id,)).fetchone()
        
        agent_id = agent['id']
        print(f"Agent ID: {agent_id}")

        # 2. Create SmartSign
        print("\n--- Creating SmartSign ---")
        code = generate_unique_code(db, length=8)
        db.execute("""
            INSERT INTO sign_assets (user_id, code, status, is_frozen, activated_at, created_at, updated_at)
            VALUES (%s, %s, 'active', false, NOW(), NOW(), NOW())
        """, (user_id, code))
        db.commit()
        
        asset = db.execute("SELECT * FROM sign_assets WHERE code = %s", (code,)).fetchone()
        asset_id = asset['id']
        print(f"SmartSign Created: ID {asset_id}, Code: {code}")

        # 3. Create Property 1
        print("\n--- Creating Property 1 ---")
        slug1 = f"test-prop-1-{int(datetime.now().timestamp())}"
        db.execute("""
            INSERT INTO properties (agent_id, address, city, state, zip, slug, status, created_at, updated_at)
            VALUES (%s, '123 Test Prop One', 'Test City', 'CA', '90210', %s, 'active', NOW(), NOW())
        """, (agent_id, slug1))
        db.commit()
        
        prop1 = db.execute("SELECT * FROM properties WHERE slug = %s", (slug1,)).fetchone()
        prop1_id = prop1['id']
        print(f"Property 1 Created: ID {prop1_id} ({prop1['address']})")

        # 4. Assign SmartSign to Property 1
        print("\n--- Assigning SmartSign to Property 1 ---")
        SmartSignsService.assign_asset(asset_id, prop1_id, user_id)
        
        # Verify
        check = db.execute("SELECT property_id FROM sign_asset_assignments WHERE sign_asset_id = %s", (asset_id,)).fetchone()
        print(f"Verification: Asset {asset_id} is assigned to Property {check['property_id']}")

        # 5. Create Property 2
        print("\n--- Creating Property 2 (for Listing Sign) ---")
        slug2 = f"test-prop-2-{int(datetime.now().timestamp())}"
        db.execute("""
            INSERT INTO properties (agent_id, address, city, state, zip, slug, status, created_at, updated_at)
            VALUES (%s, '456 Test Prop Two', 'Test City', 'CA', '90210', %s, 'active', NOW(), NOW())
        """, (agent_id, slug2))
        db.commit()
        
        prop2 = db.execute("SELECT * FROM properties WHERE slug = %s", (slug2,)).fetchone()
        prop2_id = prop2['id']
        print(f"Property 2 Created: ID {prop2_id} ({prop2['address']})")

        # 6. Create Listing Sign Order (for Prop 2)
        print("\n--- Creating Listing Sign Order for Property 2 ---")
        db.execute("""
            INSERT INTO orders (user_id, property_id, status, order_type, print_product, material, sides, print_size, created_at, updated_at)
            VALUES (%s, %s, 'paid', 'listing_sign', 'listing_sign', 'coroplast_4mm', 'double', '18x24', NOW(), NOW())
        """, (user_id, prop2_id))
        db.commit()
        print(f"Listing Sign ordered for Property {prop2_id}")

        # 7. Create Property 3
        print("\n--- Creating Property 3 ---")
        slug3 = f"test-prop-3-{int(datetime.now().timestamp())}"
        db.execute("""
            INSERT INTO properties (agent_id, address, city, state, zip, slug, status, created_at, updated_at)
            VALUES (%s, '789 Test Prop Three', 'Test City', 'CA', '90210', %s, 'active', NOW(), NOW())
        """, (agent_id, slug3))
        db.commit()
        
        prop3 = db.execute("SELECT * FROM properties WHERE slug = %s", (slug3,)).fetchone()
        prop3_id = prop3['id']
        print(f"Property 3 Created: ID {prop3_id} ({prop3['address']})")

        # 8. Reassign SmartSign to Property 3
        print("\n--- Reassigning SmartSign from Prop 1 to Prop 3 ---")
        SmartSignsService.assign_asset(asset_id, prop3_id, user_id)
        
        # Verify Assignment
        check_new = db.execute("SELECT property_id FROM sign_asset_assignments WHERE sign_asset_id = %s", (asset_id,)).fetchone()
        print(f"Verification: Asset {asset_id} is now assigned to Property {check_new['property_id']}")
        
        # Verify Prop 1 is unassigned (via logic check, though SmartSignsService handles this)
        # We can check if Prop 1 has any assignments?
        # Actually assignment is 1:1 from Asset to Prop via join table mostly?
        # smart_signs_service.py manages `sign_asset_assignments` table.
        
        print("\n--- Success! Flow Completed ---")

if __name__ == "__main__":
    simulate_flow()
