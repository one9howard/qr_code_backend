import os
import stripe
import sys
from dotenv import load_dotenv

# Load env vars from .env file in parent directory
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(base_dir, '.env'))

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

# Mapping Canonical Size -> Desired Lookup Key
SIZES = {
    "12x18": "sign_12x18",
    "18x24": "sign_18x24",
    "24x36": "sign_24x36",
    "36x18": "sign_36x18",
}

def set_keys():
    print("--- Syncing Stripe Lookup Keys ---")
    
    for size, lookup_key in SIZES.items():
        # Read price ID from env
        env_var = f"STRIPE_PRICE_SIGN_{size.upper()}"
        price_id = os.getenv(env_var)
        
        if not price_id:
            print(f"[SKIP] {size}: {env_var} not found in .env")
            continue
            
        try:
            # 1. Retrieve Price
            price = stripe.Price.retrieve(price_id)
            
            # 2. Check existing key
            if price.lookup_key == lookup_key:
                print(f"[OK]   {size}: {price_id} already has key '{lookup_key}'")
                continue
                
            # 3. Update Price
            stripe.Price.modify(price_id, lookup_key=lookup_key)
            print(f"[DONE] {size}: Set {price_id} lookup_key to '{lookup_key}'")
            
        except stripe.error.StripeError as e:
            print(f"[FAIL] {size}: Could not update {price_id}. Error: {str(e)}")
        except Exception as e:
            print(f"[FAIL] {size}: Unexpected error. {str(e)}")

    print("\n--- Sync Complete ---")

if __name__ == "__main__":
    if not stripe.api_key:
        print("ERROR: STRIPE_SECRET_KEY not found. Please check your .env file.")
    else:
        set_keys()
