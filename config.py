import os
import logging
from urllib.parse import urlparse

from utils.env import get_env_str, get_env_bool

logger = logging.getLogger(__name__)

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# -----------------------------------------------------------------------------
# Dotenv loading (LOCAL ONLY)
# -----------------------------------------------------------------------------
# Rules:
# - Railway must be configured via real environment variables (Railway dashboard).
# - Tests must be deterministic and must NOT implicitly ingest a developer's repo-root .env.
# - Local dev may use .env for convenience.
_RUNNING_ON_RAILWAY = bool(os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("RAILWAY_PROJECT_ID"))
_FLASK_ENV_EARLY = (os.getenv("FLASK_ENV") or "").strip().lower()

if (not _RUNNING_ON_RAILWAY) and (_FLASK_ENV_EARLY not in {"test", "testing"}):
    try:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=os.path.join(BASE_DIR, ".env"), override=False)
    except Exception:
        # Dotenv is convenience for local dev; failure to load should not crash.
        pass

# -----------------------------------------------------------------------------
# Environment / Stage
# -----------------------------------------------------------------------------
def _normalize_stage(raw: str) -> str:
    raw = (raw or "").strip().lower()
    if raw in {"prod", "production"}:
        return "production"
    if raw in {"stage", "staging"}:
        return "staging"
    if raw in {"test", "testing"}:
        return "test"
    return "dev"


FLASK_ENV = (os.getenv("FLASK_ENV", "development") or "development").strip().lower()
APP_STAGE = _normalize_stage(os.getenv("APP_STAGE", "dev"))

IS_TEST = APP_STAGE == "test" or FLASK_ENV in {"test", "testing"}
IS_STAGING = APP_STAGE == "staging"
IS_PRODUCTION = APP_STAGE == "production"

# Back-compat: some callers may still look for these
DEBUG = FLASK_ENV != "production" and not IS_PRODUCTION
TESTING = IS_TEST
ENV = FLASK_ENV

# -----------------------------------------------------------------------------
# Instance / Storage Paths
# -----------------------------------------------------------------------------
INSTANCE_DIR = get_env_str("INSTANCE_DIR", default=os.path.join(BASE_DIR, "instance"))

try:
    os.makedirs(INSTANCE_DIR, exist_ok=True)
except OSError as e:
    logger.warning(
        f"[Config] WARNING: Could not create INSTANCE_DIR at {INSTANCE_DIR} ({e}). Falling back to /tmp/instance."
    )
    INSTANCE_DIR = os.path.join("/tmp", "instance")
    os.makedirs(INSTANCE_DIR, exist_ok=True)

PRIVATE_DIR = os.path.join(INSTANCE_DIR, "private")
PRIVATE_PDF_DIR = os.path.join(PRIVATE_DIR, "pdf")
PRIVATE_PREVIEW_DIR = os.path.join(PRIVATE_DIR, "previews")

PRINT_INBOX_DIR = get_env_str("PRINT_INBOX_DIR", default=os.path.join(INSTANCE_DIR, "print_inbox"))

QR_PATH = os.path.join(INSTANCE_DIR, "qr")
SIGN_PATH = os.path.join(INSTANCE_DIR, "signs")
UPLOAD_DIR = os.path.join(INSTANCE_DIR, "uploads")
PROPERTY_PHOTOS_DIR = os.path.join(UPLOAD_DIR, "properties")

PROPERTY_PHOTOS_KEY_PREFIX = "uploads/properties"
AGENT_PHOTOS_KEY_PREFIX = "uploads/agents"

STATIC_DIR = os.path.join(BASE_DIR, "static")
PDF_PATH = os.path.join(STATIC_DIR, "pdf")

# -----------------------------------------------------------------------------
# URLs
# -----------------------------------------------------------------------------
def _strip_trailing_slash(url: str) -> str:
    return url[:-1] if url.endswith("/") else url


BASE_URL = _strip_trailing_slash(get_env_str("BASE_URL", default="http://localhost:5000"))
PUBLIC_BASE_URL = _strip_trailing_slash(get_env_str("PUBLIC_BASE_URL", default=BASE_URL))


def _require_https(name: str, value: str) -> None:
    if not value.lower().startswith("https://"):
        raise RuntimeError(f"CRITICAL: {name} must be HTTPS in {APP_STAGE} stage. Got: {value}")


def _forbid_substrings(name: str, value: str, forbidden: list[str]) -> None:
    lower = value.lower()
    for s in forbidden:
        if s in lower:
            raise RuntimeError(
                f"CRITICAL: {name} contains forbidden string '{s}' in {APP_STAGE} stage. Link safety violated."
            )


# Staging & production should never emit localhost/127.0.0.1 in QR codes.
# Production has an extra safety rail: forbid the literal "staging" in PUBLIC_BASE_URL.
if IS_STAGING or IS_PRODUCTION:
    if not os.getenv("PUBLIC_BASE_URL"):
        raise RuntimeError(f"CRITICAL: PUBLIC_BASE_URL environment variable is required in {APP_STAGE} stage.")

    _require_https("PUBLIC_BASE_URL", PUBLIC_BASE_URL)

    if IS_PRODUCTION:
        _forbid_substrings("PUBLIC_BASE_URL", PUBLIC_BASE_URL, ["staging", "localhost", "127.0.0.1"])
    else:
        _forbid_substrings("PUBLIC_BASE_URL", PUBLIC_BASE_URL, ["localhost", "127.0.0.1"])

# -----------------------------------------------------------------------------
# Database (Postgres-only)
# -----------------------------------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    if os.environ.get("ALLOW_MISSING_DB"):
        logger.warning("DATABASE_URL missing but ALLOW_MISSING_DB set. Using dummy.")
        DATABASE_URL = "sqlite:///:memory:"
    else:
        raise RuntimeError("DATABASE_URL environment variable is required.")

# Normalize postgres:// -> postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    os.environ["DATABASE_URL"] = DATABASE_URL

if not DATABASE_URL.startswith("postgresql://"):
    # Never include credentials in errors/logs.
    try:
        p = urlparse(DATABASE_URL)
        got = f"{p.scheme}://{p.hostname}" if p.scheme else "INVALID_URL"
    except Exception:
        got = "INVALID_URL"
    raise ValueError(
        f"CRITICAL: DATABASE_URL must be a PostgreSQL URL (postgresql://...). Got: {got}. Non-Postgres DBs are forbidden."
    )

# -----------------------------------------------------------------------------
# Storage Backend
# -----------------------------------------------------------------------------
STORAGE_BACKEND = get_env_str("STORAGE_BACKEND", default="local").strip().lower()

if IS_PRODUCTION and STORAGE_BACKEND != "s3":
    raise RuntimeError("CRITICAL: STORAGE_BACKEND must be 's3' in production.")

# In staging we strongly prefer S3 (so you don't discover S3 bugs at launch),
# but we don't hard-fail to keep staging flexible.
if IS_STAGING and STORAGE_BACKEND != "s3":
    logger.warning("[Config] WARNING: STORAGE_BACKEND is not 's3' in staging. Expect drift vs production.")

S3_BUCKET = get_env_str("S3_BUCKET", default="")  # required when STORAGE_BACKEND=s3
S3_PREFIX = get_env_str("S3_PREFIX", default="")

_region = get_env_str("AWS_REGION", default="us-east-1")
if " " in _region or not _region.replace("-", "").isalnum():
    logger.warning(f"[Config] WARNING: Invalid AWS_REGION detected: '{_region}'. Defaulting to 'us-east-1'.")
    _region = "us-east-1"
AWS_REGION = _region

if STORAGE_BACKEND == "s3":
    if not S3_BUCKET:
        raise RuntimeError("CRITICAL: S3_BUCKET must be set when STORAGE_BACKEND=s3.")
    # AWS creds may be injected by IAM role in some environments; only enforce if explicitly provided.
    # (If you are *not* using roles, set AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY in the environment.)

# -----------------------------------------------------------------------------
# Secrets
# -----------------------------------------------------------------------------
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    if IS_STAGING or IS_PRODUCTION:
        raise ValueError(f"SECRET_KEY must be set in {APP_STAGE} environment.")
    SECRET_KEY = "dev-secret-key-change-this"
    logger.warning("[Config] WARNING: Using default SECRET_KEY for development. DO NOT use in real environments!")

PRINT_JOBS_TOKEN = get_env_str("PRINT_JOBS_TOKEN") or get_env_str("PRINT_SERVER_TOKEN")
if not PRINT_JOBS_TOKEN:
    if IS_STAGING or IS_PRODUCTION:
        raise ValueError(f"PRINT_JOBS_TOKEN (or PRINT_SERVER_TOKEN) must be set in {APP_STAGE} environment.")
    PRINT_JOBS_TOKEN = "dev-print-token"
    logger.warning("[Config] WARNING: Using default PRINT_JOBS_TOKEN for development.")

# -----------------------------------------------------------------------------
# Proxy / Cookie Security
# -----------------------------------------------------------------------------
TRUST_PROXY_HEADERS = get_env_bool("TRUST_PROXY_HEADERS", default=False)
PROXY_FIX_NUM_PROXIES = int(os.environ.get("PROXY_FIX_NUM_PROXIES", "1"))

IS_SECURE_ENV = IS_STAGING or IS_PRODUCTION
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = IS_SECURE_ENV
REMEMBER_COOKIE_HTTPONLY = True
REMEMBER_COOKIE_SECURE = IS_SECURE_ENV
PREFERRED_URL_SCHEME = "https" if IS_SECURE_ENV else "http"

# -----------------------------------------------------------------------------
# Stripe
# -----------------------------------------------------------------------------
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY")
STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

_STRIPE_REQUIRED = IS_STAGING or IS_PRODUCTION
if _STRIPE_REQUIRED and not STRIPE_SECRET_KEY:
    raise ValueError(f"Missing STRIPE_SECRET_KEY in {APP_STAGE} environment.")

if STRIPE_PUBLISHABLE_KEY:
    if IS_STAGING and STRIPE_PUBLISHABLE_KEY.startswith("pk_live_"):
        raise ValueError("SAFETY RAIL: Live Stripe publishable key is forbidden in staging.")
    if IS_PRODUCTION and STRIPE_PUBLISHABLE_KEY.startswith("pk_test_"):
        raise ValueError("SAFETY RAIL: Test Stripe publishable key is forbidden in production.")

if STRIPE_SECRET_KEY:
    if IS_STAGING and STRIPE_SECRET_KEY.startswith("sk_live_"):
        raise ValueError("SAFETY RAIL: Live Stripe secret key is forbidden in staging.")
    if IS_PRODUCTION and STRIPE_SECRET_KEY.startswith("sk_test_"):
        raise ValueError("SAFETY RAIL: Test Stripe secret key is forbidden in production.")

# Stripe Prices (legacy + per-size)
STRIPE_PRICE_MONTHLY = os.environ.get("STRIPE_PRICE_MONTHLY", "")
STRIPE_PRICE_ANNUAL = os.environ.get("STRIPE_PRICE_ANNUAL", "")
STRIPE_PRICE_ID_PRO = os.environ.get("STRIPE_PRICE_ID_PRO", "")
STRIPE_PRICE_LISTING_KIT = os.environ.get("STRIPE_PRICE_LISTING_KIT", "")
STRIPE_PRICE_LISTING_UNLOCK = os.environ.get("STRIPE_PRICE_LISTING_UNLOCK", "")

# If your code uses a single "sign" and "smartsign" price, keep these.
STRIPE_PRICE_SIGN = os.environ.get("STRIPE_PRICE_SIGN", "")
STRIPE_PRICE_SMARTSIGN = os.environ.get("STRIPE_PRICE_SMARTSIGN", "")

# If your code uses per-size prices, keep these too (optional).
STRIPE_PRICE_SIGN_12X18 = os.environ.get("STRIPE_PRICE_SIGN_12X18", "")
STRIPE_PRICE_SIGN_18X24 = os.environ.get("STRIPE_PRICE_SIGN_18X24", "")
STRIPE_PRICE_SIGN_24X18 = os.environ.get("STRIPE_PRICE_SIGN_24X18", "")
STRIPE_PRICE_SIGN_24X36 = os.environ.get("STRIPE_PRICE_SIGN_24X36", "")
STRIPE_PRICE_SIGN_36X24 = os.environ.get("STRIPE_PRICE_SIGN_36X24", "")

STRIPE_PRICE_SMARTSIGN_12X18 = os.environ.get("STRIPE_PRICE_SMARTSIGN_12X18", "")
STRIPE_PRICE_SMARTSIGN_18X24 = os.environ.get("STRIPE_PRICE_SMARTSIGN_18X24", "")
STRIPE_PRICE_SMARTSIGN_24X18 = os.environ.get("STRIPE_PRICE_SMARTSIGN_24X18", "")
STRIPE_PRICE_SMARTSIGN_24X36 = os.environ.get("STRIPE_PRICE_SMARTSIGN_24X36", "")
STRIPE_PRICE_SMARTSIGN_36X24 = os.environ.get("STRIPE_PRICE_SMARTSIGN_36X24", "")

# Checkout URLs
STRIPE_SIGN_SUCCESS_URL = os.environ.get(
    "STRIPE_SIGN_SUCCESS_URL", f"{BASE_URL}/order/success?session_id={{CHECKOUT_SESSION_ID}}"
)
STRIPE_SIGN_CANCEL_URL = os.environ.get("STRIPE_SIGN_CANCEL_URL", f"{BASE_URL}/order/cancel")
STRIPE_SUCCESS_URL = os.environ.get(
    "STRIPE_SUCCESS_URL", f"{BASE_URL}/billing/success?session_id={{CHECKOUT_SESSION_ID}}"
)
STRIPE_CANCEL_URL = os.environ.get("STRIPE_CANCEL_URL", f"{BASE_URL}/billing/cancel")
STRIPE_PORTAL_RETURN_URL = os.environ.get("STRIPE_PORTAL_RETURN_URL", f"{BASE_URL}/dashboard")

# -----------------------------------------------------------------------------
# Mail (optional)
# -----------------------------------------------------------------------------
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
SMTP_USE_TLS = get_env_bool("SMTP_USE_TLS", default=True)

MAILJET_API_KEY = os.environ.get("MAILJET_API_KEY", "")
MAILJET_SECRET_KEY = os.environ.get("MAILJET_SECRET_KEY", "")

# -----------------------------------------------------------------------------
# Upload limits
# -----------------------------------------------------------------------------
MAX_CONTENT_LENGTH = 16 * 1024 * 1024

# -----------------------------------------------------------------------------
# Feature Flags
# -----------------------------------------------------------------------------
ENABLE_SMART_RISER = get_env_bool("ENABLE_SMART_RISER", default=False)
if IS_PRODUCTION or IS_STAGING:
    ENABLE_SMART_RISER = False
ENABLE_QR_LOGO = get_env_bool("ENABLE_QR_LOGO", default=False)