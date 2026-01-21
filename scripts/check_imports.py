
import sys
import os

# Add project root to sys.path
sys.path.append(os.getcwd())

print("--- Starting Import Check ---")

try:
    print("1. Importing config...")
    import config
    
    print("2. Importing database...")
    import database
    
    print("3. Importing models...")
    import models
    
    print("4. Importing services...")
    import services.print_catalog
    import services.fulfillment
    import services.gating
    
    print("5. Importing routes...")
    from routes import orders, smart_signs, smart_riser, printing, agent, dashboard, admin
    
    print("6. Importing app...")
    from app import create_app
    
    print("7. Creating app instance...")
    app = create_app()
    print("--- SUCCESS: App created successfully ---")

except Exception as e:
    print(f"\nCRITICAL FAILURE during step: {sys.exc_info()[0].__name__}")
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
