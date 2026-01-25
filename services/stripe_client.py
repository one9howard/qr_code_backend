
import os
import stripe
import logging

logger = logging.getLogger(__name__)

def init_stripe(app):
    """
    Centralized Stripe Initialization.
    Checks environment safety and sets API Key.
    """
    secret_key = app.config.get('STRIPE_SECRET_KEY')
    stage = app.config.get('APP_STAGE')
    
    if not secret_key:
        if stage in ('prod', 'staging'):
            raise RuntimeError("Missing STRIPE_SECRET_KEY in production/staging.")
        else:
            logger.warning("Missing STRIPE_SECRET_KEY (Dev Mode). Stripe calls will fail.")
            return

    stripe.api_key = secret_key
    
    # Strict Environment Safety
    is_live_key = secret_key.startswith('sk_live_')
    
    if stage == 'prod' and not is_live_key:
         # Phase 6: Fail Hard if Prod uses Test Key
         raise RuntimeError("Configuration Error: Using TEST Stripe Key in PROD environment.")
         
    if stage in ('dev', 'test', 'staging') and is_live_key:
         # Phase 6: Protect against accidental real charges
         raise RuntimeError(f"SAFETY RAIL: Attempted to use LIVE Stripe Key in '{stage}' environment.")

    logger.info(f"Stripe initialized for stage={stage} (Live={is_live_key})")
