import os
import tempfile
from utils.env import get_env_str, get_env_bool

# Only load .env in development. In production, config comes from environment variables (ECS/Docker).
from dotenv import load_dotenv
load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Instance Directory - All runtime state goes here
INSTANCE_DIR = get_env_str("INSTANCE_DIR", default=os.path.join(BASE_DIR, "instance"))

# Verify permissions / create instance dir immediately so derived paths are correct
try:
    os.makedirs(INSTANCE_DIR, exist_ok=True)
except OSError as e:
    print(f"[Config] WARNING: Could not create INSTANCE_DIR at {INSTANCE_DIR} ({e}). Falling back to /tmp/instance.")
    # Force /tmp because tempfile.gettempdir() might return /temp which is read-only in this env
    INSTANCE_DIR = os.path.join("/tmp", "instance")
    os.makedirs(INSTANCE_DIR, exist_ok=True)

# Private (non-public) storage for sensitive files
PRIVATE_DIR = os.path.join(INSTANCE_DIR, "private")
PRIVATE_PDF_DIR = os.path.join(PRIVATE_DIR, "pdf")
PRIVATE_PREVIEW_DIR = os.path.join(PRIVATE_DIR, "previews")

# Database (Postgres-only)
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is required.")

if not DATABASE_URL.startswith("postgres"):
    # Never include credentials in errors/logs.
    try:
        from urllib.parse import urlparse
        p = urlparse(DATABASE_URL)
        got = f"{p.scheme}://{p.hostname}" if p.scheme else "INVALID_URL"
    except Exception:
        got = "INVALID_URL"
    raise ValueError(
        f"CRITICAL: DATABASE_URL must be a PostgreSQL URL. Got: {got}. Non-Postgres DBs are strictly forbidden."
    )

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    os.environ["DATABASE_URL"] = DATABASE_URL

# Storage Configuration
STORAGE_BACKEND = get_env_str("STORAGE_BACKEND", default="local")
S3_BUCKET = get_env_str("S3_BUCKET")

# Validate output region to avoid crashes if user provides garbage
_region = get_env_str("AWS_REGION", default="us-east-1")
if " " in _region or not _region.replace("-", "").isalnum():
    print(f"[Config] WARNING: Invalid AWS_REGION detected: '{_region}'. Defaulting to 'us-east-1'.")
    _region = "us-east-1"
AWS_REGION = _region

S3_PREFIX = get_env_str("S3_PREFIX", default="")

# Private storage & Inbox
PRINT_INBOX_DIR = get_env_str("PRINT_INBOX_DIR", default=os.path.join(INSTANCE_DIR, "print_inbox"))

# User-Generated Content Directories
QR_PATH = os.path.join(INSTANCE_DIR, "qr")
SIGN_PATH = os.path.join(INSTANCE_DIR, "signs")
UPLOAD_DIR = os.path.join(INSTANCE_DIR, "uploads")
PROPERTY_PHOTOS_DIR = os.path.join(UPLOAD_DIR, "properties")

# Storage Key Prefixes (Relative paths for S3/Local Storage)
PROPERTY_PHOTOS_KEY_PREFIX = "uploads/properties"
AGENT_PHOTOS_KEY_PREFIX = "uploads/agents"

# Static directory
STATIC_DIR = os.path.join(BASE_DIR, "static")
PDF_PATH = os.path.join(STATIC_DIR, "pdf")

# URLs
BASE_URL = get_env_str("BASE_URL", default="http://192.168.1.186:5000")

# Security: SECRET_KEY
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    if os.environ.get("FLASK_ENV") == "production":
        raise ValueError("SECRET_KEY must be set in production environment.")
    else:
        SECRET_KEY = "dev-secret-key-change-this"
        print("[WARNING] Using default SECRET_KEY for development. DO NOT use in production!")

# File Upload Security
MAX_CONTENT_LENGTH = 16 * 1024 * 1024

# Print Server Security
PRINT_JOBS_TOKEN = get_env_str("PRINT_JOBS_TOKEN")
if not PRINT_JOBS_TOKEN:
    if os.environ.get("FLASK_ENV") == "production":
        raise ValueError("PRINT_JOBS_TOKEN must be set in production environment.")
    else:
        PRINT_JOBS_TOKEN = "dev-print-token"
        print("[WARNING] Using default PRINT_JOBS_TOKEN for development.")

# Trust Proxy Headers (for running behind load balancers/reverse proxies)
TRUST_PROXY_HEADERS = get_env_bool("TRUST_PROXY_HEADERS", default=False)
PROXY_FIX_NUM_PROXIES = int(os.environ.get("PROXY_FIX_NUM_PROXIES", "1"))

# Environment Stage
APP_STAGE = os.environ.get("APP_STAGE", "dev") # dev, staging, prod
FLASK_ENV = os.environ.get("FLASK_ENV", "development")
IS_PRODUCTION = (FLASK_ENV == "production")

# Stripe Configuration
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY")
STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET")

if STRIPE_PUBLISHABLE_KEY:
    is_live_pk = STRIPE_PUBLISHABLE_KEY.startswith("pk_live_")
    if APP_STAGE != "prod" and is_live_pk:
        raise ValueError(f"SAFETY RAIL: Attempted to use Live Stripe Publishable Key in '{APP_STAGE}' stage.")

# Allow running without keys in debug mode, but fail in production if needed
if not STRIPE_SECRET_KEY:
    if os.environ.get("FLASK_ENV") == "production":
        raise ValueError("Missing STRIPE_SECRET_KEY in production environment.")
    else:
        STRIPE_SECRET_KEY = "sk_test_placeholder"
        STRIPE_PUBLISHABLE_KEY = "pk_test_placeholder"
        STRIPE_WEBHOOK_SECRET = "" 

# Stripe Prices
STRIPE_PRICE_MONTHLY = os.environ.get("STRIPE_PRICE_MONTHLY", "price_monthly_id")
STRIPE_PRICE_ANNUAL = os.environ.get("STRIPE_PRICE_ANNUAL", "price_annual_id")
STRIPE_PRICE_ID_PRO = os.environ.get("STRIPE_PRICE_ID_PRO", "price_pro_id")
STRIPE_PRICE_LISTING_KIT = os.environ.get("STRIPE_PRICE_LISTING_KIT", "price_listing_kit_id")

# Validate Stripe Price IDs in production
if os.environ.get("FLASK_ENV") == "production":
    _placeholder_prices = []
    # Check a few critical ones
    if STRIPE_PRICE_MONTHLY.startswith("price_monthly_id"): _placeholder_prices.append("STRIPE_PRICE_MONTHLY")
    
    if _placeholder_prices:
        print(f"[Config] WARNING: Placeholder prices detected in production: {_placeholder_prices}")

STRIPE_SIGN_SUCCESS_URL = os.environ.get("STRIPE_SIGN_SUCCESS_URL", f"{BASE_URL}/order/success?session_id={{CHECKOUT_SESSION_ID}}")
STRIPE_SIGN_CANCEL_URL = os.environ.get("STRIPE_SIGN_CANCEL_URL", f"{BASE_URL}/order/cancel")

# Generic Billing / Subscription URLs
STRIPE_SUCCESS_URL = os.environ.get("STRIPE_SUCCESS_URL", f"{BASE_URL}/billing/success?session_id={{CHECKOUT_SESSION_ID}}")
STRIPE_CANCEL_URL = os.environ.get("STRIPE_CANCEL_URL", f"{BASE_URL}/billing/cancel")
STRIPE_PORTAL_RETURN_URL = os.environ.get("STRIPE_PORTAL_RETURN_URL", f"{BASE_URL}/dashboard")

# Cookie Security
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_SECURE = IS_PRODUCTION
REMEMBER_COOKIE_HTTPONLY = True
REMEMBER_COOKIE_SECURE = IS_PRODUCTION
PREFERRED_URL_SCHEME = 'https' if IS_PRODUCTION else 'http'

# Feature Flags
ENABLE_SMART_RISER = get_env_bool('ENABLE_SMART_RISER', default=False)

