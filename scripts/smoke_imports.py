#!/usr/bin/env python3
import os
import sys

# Add project root to path
sys.path.insert(0, os.getcwd())

# Minimal environment for safe imports
os.environ["DATABASE_URL"] = "postgresql://user:pass@localhost:5432/dbname"
os.environ["SECRET_KEY"] = "smoke-test-secret"
os.environ["PRINT_JOBS_TOKEN"] = "smoke-test-token"
os.environ["FLASK_ENV"] = "development"

def smoke_test():
    print("[Smoke Check] Testing critical imports...")
    try:
        # Import services
        print("  - Importing services.printing.layout_utils...")
        import services.printing.layout_utils
        
        print("  - Importing services.pdf_smartsign...")
        import services.pdf_smartsign
        
        # Import and create app to verify blueprints
        print("  - Creating Flask app and verifying blueprints...")
        from app import create_app
        app = create_app()
        
        print("[Smoke Check] All critical imports and app creation PASSED.")
        return True
    except Exception as e:
        print(f"[Smoke Check] FAILED with error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    if smoke_test():
        sys.exit(0)
    else:
        sys.exit(1)
