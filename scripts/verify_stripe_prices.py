#!/usr/bin/env python
"""
Diagnostic script: Verify Stripe Price mappings for all sign sizes.
Run from project root: python scripts/verify_stripe_prices.py
"""
import os
import sys

# Path hack for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import stripe
from config import STRIPE_SECRET_KEY
from services.stripe_prices import verify_price_mappings, get_lookup_keys_for_size

stripe.api_key = STRIPE_SECRET_KEY

def main():
    print("=" * 60)
    print("STRIPE PRICE MAPPING VERIFICATION")
    print("=" * 60)
    
    if not stripe.api_key or stripe.api_key.startswith("sk_test_placeholder"):
        print("\nERROR: STRIPE_SECRET_KEY not configured properly.")
        print("Please check your .env file.")
        return
    
    print(f"\nUsing Stripe API Key: {stripe.api_key[:12]}...")
    print()
    
    results = verify_price_mappings()
    
    all_ok = True
    for size, result in results.items():
        print(f"--- Size: {size} ---")
        print(f"  Lookup Keys Tried: {result['lookup_keys_attempted']}")
        
        if result['status'] == 'OK':
            print(f"  Status: ✅ OK")
            print(f"  Resolved Key: {result['resolved_key']}")
            print(f"  Price ID: {result['resolved_price_id']}")
            print(f"  Product ID: {result['resolved_product_id']}")
            print(f"  Amount: ${result['resolved_amount']:.2f} {result['resolved_currency']}")
        else:
            print(f"  Status: ❌ FAILED")
            print(f"  Error: {result['error']}")
            all_ok = False
        print()
    
    print("=" * 60)
    if all_ok:
        print("✅ All price mappings verified successfully!")
    else:
        print("❌ Some price mappings failed. Check Stripe Dashboard.")
        print("\nTo fix:")
        print("1. Go to Stripe Dashboard > Products")
        print("2. Create/Edit prices with lookup keys: 12x18_sign, 18x24_sign, etc.")
        print("3. Make sure products are ACTIVE (not archived)")
    print("=" * 60)

if __name__ == "__main__":
    main()
