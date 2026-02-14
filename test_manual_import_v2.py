import sys
import os

# Mock ENV
os.environ['DATABASE_URL'] = 'postgresql://mock:mock@localhost/mock'
os.environ['SECRET_KEY'] = 'mock-secret-key'
# CHANGE: Set FLASK_ENV to testing to skip cache warm
os.environ['FLASK_ENV'] = 'testing' 
os.environ['APP_STAGE'] = 'staging'
os.environ['STORAGE_BACKEND'] = 's3'
os.environ['S3_BUCKET'] = 'mock-bucket'
os.environ['AWS_REGION'] = 'us-east-1'
os.environ['PUBLIC_BASE_URL'] = 'https://example.com'
os.environ['STRIPE_SECRET_KEY'] = 'sk_test_mock'
os.environ['STRIPE_PUBLISHABLE_KEY'] = 'pk_test_mock'
os.environ['PRINT_JOBS_TOKEN'] = 'mock-print-token'

try:
    print("   Attempting 'import app'...")
    import app
    import extensions
    print("   [OK] Import successful.")
except ImportError as e:
    print(f"   [FAIL] ImportError: {e}")
    sys.exit(1)
except Exception as e:
    print(f"   [FAIL] Validation Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
