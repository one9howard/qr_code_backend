import os
import stripe
import time

# Constants for Price IDs (from Env)
# These should be set in .env
STRIPE_PRICE_MONTHLY = os.environ.get('STRIPE_PRICE_MONTHLY')
STRIPE_PRICE_ANNUAL = os.environ.get('STRIPE_PRICE_ANNUAL')
STRIPE_PRICE_LISTING_UNLOCK = os.environ.get('STRIPE_PRICE_LISTING_UNLOCK')

class PriceCache:
    """
    Simple in-memory cache for Stripe Price objects to avoid API rate limits.
    """
    _cache = {}
    _expiry = {}
    TTL = 3600  # 1 hour cache

    @classmethod
    def get(cls, price_id):
        if not price_id:
            # Return dummy if not configured, or None
            return None
            
        now = time.time()
        if price_id in cls._cache and cls._expiry.get(price_id, 0) > now:
            return cls._cache[price_id]
        
        # Fetch from Stripe
        try:
            # stripe.api_key handled by app.py init_stripe
            if not stripe.api_key:
                return None
                
            price = stripe.Price.retrieve(price_id)
            
            # Format Amount (e.g. 999 -> $9.99, 1000 -> $10)
            amount_dollars = price.unit_amount / 100
            if amount_dollars.is_integer():
                formatted = f"${int(amount_dollars)}"
            else:
                formatted = f"${amount_dollars:.2f}"
            
            data = {
                "id": price.id,
                "amount": price.unit_amount, # cents
                "currency": price.currency,
                "formatted": formatted,
                "interval": price.recurring.interval if price.recurring else "one-time"
            }
            
            cls._cache[price_id] = data
            cls._expiry[price_id] = now + cls.TTL
            return data
            
        except Exception as e:
            print(f"[StripeConfig] Error fetching price {price_id}: {e}")
            return None

def get_configured_prices():
    """
    Returns a dict of configured price objects.
    Keys: 'monthly', 'annual', 'unlock'
    """
    return {
        "monthly": PriceCache.get(STRIPE_PRICE_MONTHLY),
        "annual": PriceCache.get(STRIPE_PRICE_ANNUAL),
        "unlock": PriceCache.get(STRIPE_PRICE_LISTING_UNLOCK),
    }

def get_unlock_price_id():
    return STRIPE_PRICE_LISTING_UNLOCK
