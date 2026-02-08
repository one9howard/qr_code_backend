
import os
import stripe
import logging

logger = logging.getLogger(__name__)

from config import IS_PRODUCTION, IS_STAGING, APP_STAGE

def init_stripe(app):
    """
    Centralized Stripe Initialization.
    Checks environment safety and sets API Key.
    """
    secret_key = app.config.get('STRIPE_SECRET_KEY')
    # stage = app.config.get('APP_STAGE') # Legacy
    
    if not secret_key:
        if IS_PRODUCTION or IS_STAGING:
            raise RuntimeError("Missing STRIPE_SECRET_KEY in production/staging.")
        else:
            logger.warning("Missing STRIPE_SECRET_KEY (Dev Mode). Stripe calls will fail.")
            return

    stripe.api_key = secret_key
    
    # Strict Environment Safety
    is_live_key = secret_key.startswith('sk_live_')
    
    if IS_PRODUCTION and not is_live_key:
         # Phase 6: Fail Hard if Prod uses Test Key
         raise RuntimeError("Configuration Error: Using TEST Stripe Key in PROD environment.")
         
    if (not IS_PRODUCTION) and is_live_key:
         # Phase 6: Protect against accidental real charges (Staging must use test keys unless explicitly allowed, but here we enforce test keys for non-prod usually)
         # Wait, Staging often uses Test keys. The rule says "Live Stripe secret key is forbidden in staging" in config.py.
         # So if NOT IS_PRODUCTION and is_live_key -> ERROR.
         raise RuntimeError(f"SAFETY RAIL: Attempted to use LIVE Stripe Key in '{APP_STAGE}' environment.")

    logger.info(f"Stripe initialized for stage={APP_STAGE} (Live={is_live_key})")
