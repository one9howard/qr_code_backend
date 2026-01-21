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
        PRINT_JOBS_TOKEN = "dev-token-insecure"

# =============================================================================
# Stripe & App Stage Configuration (Safe Staging)
# =============================================================================
# Only "prod" is true production. All else ("test", "staging", "dev") is test mode.
APP_STAGE = get_env_str("APP_STAGE", default="test")

STRIPE_SECRET_KEY = get_env_str("STRIPE_SECRET_KEY")
STRIPE_PUBLISHABLE_KEY = get_env_str("STRIPE_PUBLISHABLE_KEY")
STRIPE_WEBHOOK_SECRET = get_env_str("STRIPE_WEBHOOK_SECRET")

# SAFETY RAIL: Prevent using Live keys in non-prod stages
if STRIPE_SECRET_KEY:
    is_live_key = STRIPE_SECRET_KEY.startswith("sk_live_")
    if APP_STAGE != "prod" and is_live_key:
        raise ValueError(f"SAFETY RAIL: Attempted to use Live Stripe Secret Key in '{APP_STAGE}' stage! Use 'sk_test_...' instead.")
    if APP_STAGE == "prod" and not is_live_key:
         print(f"[WARNING] Using Test Stripe Keys in PROD stage. This might be intentional locally, but unusual.")

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
STRIPE_PRICE_SIGN = os.environ.get("STRIPE_PRICE_SIGN", "price_sign_id")
STRIPE_PRICE_ID_PRO = os.environ.get("STRIPE_PRICE_ID_PRO", "price_pro_id")

STRIPE_PRICE_SIGN_12X18 = os.environ.get("STRIPE_PRICE_SIGN_12X18", "price_sign_12x18_id")
STRIPE_PRICE_SIGN_18X24 = os.environ.get("STRIPE_PRICE_SIGN_18X24", "price_sign_18x24_id")
STRIPE_PRICE_SIGN_24X36 = os.environ.get("STRIPE_PRICE_SIGN_24X36", "price_sign_24x36_id")
STRIPE_PRICE_SIGN_36X18 = os.environ.get("STRIPE_PRICE_SIGN_36X18", "price_sign_36x18_id")
STRIPE_PRICE_LISTING_KIT = os.environ.get("STRIPE_PRICE_LISTING_UNLOCK", "price_listing_lock_id")


# Validate Stripe Price IDs in production
if os.environ.get("FLASK_ENV") == "production":
    _placeholder_prices = []
    # Check a few critical ones
    if STRIPE_PRICE_MONTHLY == "price_monthly_id": _placeholder_prices.append("STRIPE_PRICE_MONTHLY")
    if STRIPE_PRICE_SIGN == "price_sign_id": _placeholder_prices.append("STRIPE_PRICE_SIGN")
    
    if _placeholder_prices:
        raise ValueError(
            f"PRODUCTION STARTUP FAILED: Stripe price IDs are placeholders: {', '.join(_placeholder_prices)}. "
            f"Set real price_xxx IDs in environment variables."
        )

# URLs
STRIPE_SUCCESS_URL = os.environ.get("STRIPE_SUCCESS_URL", f"{BASE_URL}/billing/success?session_id={{CHECKOUT_SESSION_ID}}")
STRIPE_CANCEL_URL = os.environ.get("STRIPE_CANCEL_URL", f"{BASE_URL}/billing/cancel")
STRIPE_SIGN_SUCCESS_URL = os.environ.get("STRIPE_SIGN_SUCCESS_URL", f"{BASE_URL}/order/success?session_id={{CHECKOUT_SESSION_ID}}")
STRIPE_SIGN_CANCEL_URL = os.environ.get("STRIPE_SIGN_CANCEL_URL", f"{BASE_URL}/order/cancel")
STRIPE_PORTAL_RETURN_URL = os.environ.get("STRIPE_PORTAL_RETURN_URL", f"{BASE_URL}/dashboard")

# Legal
LEGAL_CONTACT_EMAIL = get_env_str("LEGAL_CONTACT_EMAIL", default="support@yourdomain.com")

# =============================================================================
# Create Directories (only needed for local storage)
# =============================================================================
# INSTANCE_DIR created at top of file

# Only create local storage directories if not using S3 (or if using local storage)
print(f"[Config] STORAGE_BACKEND={STORAGE_BACKEND}, INSTANCE_DIR={INSTANCE_DIR}")

if STORAGE_BACKEND != "s3":
    import time
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # Creation Pass
            for d in [PRIVATE_PDF_DIR, PRIVATE_PREVIEW_DIR, PRINT_INBOX_DIR, QR_PATH, SIGN_PATH, UPLOAD_DIR, PROPERTY_PHOTOS_DIR]:
                try:
                    os.makedirs(d, exist_ok=True)
                except Exception as e:
                    print(f"[Config] Warning: makedirs failed for {d} (Attempt {attempt+1}): {e}")

            # Verification Pass
            _test_file = os.path.join(PRIVATE_PDF_DIR, ".write_test")
            with open(_test_file, "w") as f:
                f.write("test")
            os.remove(_test_file)
            print(f"[Config] Write check passed for {PRIVATE_PDF_DIR}")
            break # Success

        except (IOError, OSError) as e:
            if attempt < max_retries - 1:
                print(f"[Config] Warning: Filesystem verify failed (Attempt {attempt+1}): {e}. Retrying...")
                time.sleep(1)
                continue
            
            print(f"[CRITICAL] Cannot write to PRIVATE_PDF_DIR ({PRIVATE_PDF_DIR}): {e}")
            # Investigate parent dir details
            parent = os.path.dirname(PRIVATE_PDF_DIR)
            print(f"  Parent {parent} exists? {os.path.exists(parent)}")
            if os.path.exists(parent):
                 import stat
                 st = os.stat(parent)
                 print(f"  Parent perms: {oct(st.st_mode)}")
            # Fail silently? Or crash?
            # Allowing proceed might result in runtime errors, but we tried our best.

# Session Config
IS_PRODUCTION = os.environ.get("FLASK_ENV") == "production"

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = IS_PRODUCTION

REMEMBER_COOKIE_HTTPONLY = True
REMEMBER_COOKIE_SECURE = IS_PRODUCTION
PREFERRED_URL_SCHEME = "https" if IS_PRODUCTION else "http"

# Reverse Proxy Config
TRUST_PROXY_HEADERS = get_env_bool("TRUST_PROXY_HEADERS", False)
PROXY_FIX_NUM_PROXIES = int(get_env_str("PROXY_FIX_NUM_PROXIES", "1"))

# Production Validation (Strict)
def validate_production_config():
    if not IS_PRODUCTION:
        return

    _missing = []
    
    def is_set(val):
        return val and str(val).strip()

    if not is_set(SECRET_KEY) or SECRET_KEY == "dev-secret-key-change-this":
        _missing.append("SECRET_KEY")

    if not is_set(BASE_URL) or BASE_URL == "http://192.168.1.186:5000":
        _missing.append(f"BASE_URL (Current: '{BASE_URL}')")

    if not is_set(os.environ.get("INSTANCE_DIR")):
        _missing.append("INSTANCE_DIR")

    if not is_set(STRIPE_SECRET_KEY) or STRIPE_SECRET_KEY.startswith("sk_test_placeholder"):
        _missing.append("STRIPE_SECRET_KEY")
    if not is_set(STRIPE_PUBLISHABLE_KEY):
        _missing.append("STRIPE_PUBLISHABLE_KEY")
    if not is_set(STRIPE_WEBHOOK_SECRET):
        _missing.append("STRIPE_WEBHOOK_SECRET")

    if not is_set(PRINT_JOBS_TOKEN):
        _missing.append("PRINT_JOBS_TOKEN")
    
    # SMTP Configuration (required for lead notifications ONLY in prod)
    # Staging/Test environments can run without email
    if APP_STAGE == 'prod':
        if not is_set(os.environ.get("SMTP_HOST")):
            _missing.append("SMTP_HOST (Required for PROD)")
        if not is_set(os.environ.get("SMTP_USER")):
            _missing.append("SMTP_USER (Required for PROD)")
        if not is_set(os.environ.get("SMTP_PASS")):
            _missing.append("SMTP_PASS (Required for PROD)")
    # NOTIFY_EMAIL_FROM is optional (defaults to noreply@insitesigns.com in service)

    if _missing:
        import sys
        print("\n[CRITICAL] PRODUCTION STARTUP FAILED. Missing/Insecure Config:", file=sys.stderr)
        for m in _missing:
            print(f"  - {m}", file=sys.stderr)
        sys.exit(1)

print("[Config] Validating production config...")
validate_production_config()
print("[Config] Production config valid.")
