import os
import time
import stripe
import logging
from utils.sign_options import normalize_sign_size
from config import STRIPE_PRICE_SIGN  # Ultimate fallback

logger = logging.getLogger(__name__)

# Mapping from canonical size to Stripe Lookup Keys (in priority order)
# User's Stripe Dashboard uses format: "18x24_sign"
SIZE_TO_LOOKUP_KEYS = {
    "12x18": ["12x18_listing_sign_print", "listing_sign_print_12x18"],
    "18x24": ["18x24_listing_sign_print", "listing_sign_print_18x24"],
    "24x36": ["24x36_listing_sign_print", "listing_sign_print_24x36"],
    "36x18": ["36x18_listing_sign_print", "listing_sign_print_36x18"],
}

# Cache: {lookup_key: {"id": price_id, "product_id": prod_id, "expires_at": timestamp}}
PRICE_CACHE = {}
CACHE_TTL = 300  # 5 minutes in seconds


def get_lookup_keys_for_size(size: str) -> list[str]:
    """
    Get ordered list of lookup keys to try for a given size.
    Supports env var overrides for flexibility.
    """
    # Check for env override first
    env_key = f"STRIPE_LOOKUP_KEY_SIGN_{size.upper()}"
    override = os.getenv(env_key)
    
    keys = []
    if override:
        keys.append(override)
    
    # Add default keys from mapping
    defaults = SIZE_TO_LOOKUP_KEYS.get(size, [])
    keys.extend(defaults)
    
    # De-duplicate while preserving order
    seen = set()
    ordered = []
    for k in keys:
        if k and k not in seen:
            seen.add(k)
            ordered.append(k)
    
    return ordered


def get_price_id_for_size(raw_size: str, strict: bool = False) -> tuple[str, str | None]:
    """
    Resolve the Stripe Price ID for a given sign size using Lookup Keys.
    
    Args:
        raw_size (str): The raw size string (e.g. "12x18", "24x26").
        strict (bool): If True, raise exception instead of falling back on failure.
        
    Returns:
        tuple: (price_id, lookup_key_used)
        lookup_key_used is None if fallback was used.
        
    Raises:
        ValueError: If strict=True and no price found for any lookup key.
    """
    size = normalize_sign_size(raw_size)
    lookup_keys = get_lookup_keys_for_size(size)
    
    if not lookup_keys:
        msg = f"No lookup keys configured for size '{size}'"
        logger.error(f"[Pricing] {msg}")
        if strict:
            raise ValueError(msg)
        return _get_fallback_price(size), None

    # Try each lookup key in order
    for lookup_key in lookup_keys:
        # Check Cache
        cached = PRICE_CACHE.get(lookup_key)
        if cached and time.time() < cached['expires_at']:
            logger.info(f"[Pricing] Cache hit: size={size} key={lookup_key} price={cached['id']}")
            return cached['id'], lookup_key

        # Resolve via Stripe API
        try:
            prices = stripe.Price.list(
                lookup_keys=[lookup_key],
                active=True,
                limit=2  # Get 2 to detect duplicates
            )
            
            if prices and len(prices.data) > 0:
                price = prices.data[0]
                price_id = price.id
                product_id = price.product if isinstance(price.product, str) else price.product.id
                
                # Warn on duplicates
                if len(prices.data) > 1:
                    logger.warning(
                        f"[Pricing] DUPLICATE lookup key '{lookup_key}' found! "
                        f"Multiple prices exist. Using first: {price_id}"
                    )
                
                # Update Cache
                PRICE_CACHE[lookup_key] = {
                    "id": price_id,
                    "product_id": product_id,
                    "expires_at": time.time() + CACHE_TTL
                }
                
                logger.info(
                    f"[Pricing] Resolved: size={size} key={lookup_key} "
                    f"price={price_id} product={product_id}"
                )
                return price_id, lookup_key
                
        except stripe.error.StripeError as e:
            logger.error(f"[Pricing] Stripe API error for key '{lookup_key}': {e}")
            continue
        except Exception as e:
            logger.error(f"[Pricing] Unexpected error for key '{lookup_key}': {e}")
            continue
    
    # All lookup keys failed
    attempted = ", ".join(lookup_keys)
    logger.error(f"[Pricing] All lookup keys failed for size '{size}'. Attempted: [{attempted}]")
    
    if strict:
        raise ValueError(f"No active Stripe price found for size '{size}'. Lookup keys tried: [{attempted}]")
    
    fallback_price = _get_fallback_price(size)
    logger.error(
        f"[Pricing] FALLBACK USED for size '{size}'. "
        f"Falling back to: {fallback_price}. This may charge the wrong amount!"
    )
    return fallback_price, None


def _get_fallback_price(size: str) -> str:
    """
    Resolve price from environment variables if API lookup fails.
    """
    # 1. Try specific env var: STRIPE_PRICE_SIGN_12X18
    env_key = f"STRIPE_PRICE_SIGN_{size.upper()}"
    val = os.environ.get(env_key)
    if val:
        logger.info(f"[Pricing] Using env var fallback {env_key}={val}")
        return val
        
    # 2. Ultimate fallback from config
    logger.warning(f"[Pricing] Using global default STRIPE_PRICE_SIGN for size {size}")
    return STRIPE_PRICE_SIGN


def verify_price_mappings() -> dict:
    """
    Diagnostic function: Verify all size->price mappings.
    Returns a dict with verification results for each size.
    """
    from constants import SIGN_SIZES
    
    results = {}
    for size in SIGN_SIZES.keys():
        lookup_keys = get_lookup_keys_for_size(size)
        result = {
            "size": size,
            "lookup_keys_attempted": lookup_keys,
            "resolved_price_id": None,
            "resolved_product_id": None,
            "resolved_amount": None,
            "resolved_currency": None,
            "resolved_key": None,
            "status": "FAILED",
            "error": None,
        }
        
        try:
            price_id, used_key = get_price_id_for_size(size, strict=True)
            result["resolved_price_id"] = price_id
            result["resolved_key"] = used_key
            
            # Fetch full price details
            price = stripe.Price.retrieve(price_id, expand=["product"])
            result["resolved_product_id"] = price.product.id if hasattr(price.product, 'id') else price.product
            result["resolved_amount"] = price.unit_amount / 100 if price.unit_amount else None
            result["resolved_currency"] = price.currency.upper() if price.currency else None
            result["status"] = "OK"
            
        except ValueError as e:
            result["error"] = str(e)
        except stripe.error.StripeError as e:
            result["error"] = f"Stripe Error: {str(e)}"
        except Exception as e:
            result["error"] = f"Unexpected: {str(e)}"
            
        results[size] = result
    
    return results
