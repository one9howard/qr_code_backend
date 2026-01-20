#!/usr/bin/env python3
"""
Bootstrap Stripe Test Data
--------------------------
Creates necessary Products and Prices in your Stripe account (Test Mode)
and outputs the configuration lines for your .env file.

Usage:
    python scripts/bootstrap_stripe.py
"""
import os
import sys
import stripe
from dotenv import load_dotenv

# Load env vars
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(base_dir, '.env'))

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

if not stripe.api_key or stripe.api_key.startswith("sk_test_placeholder"):
    print("❌ ERROR: STRIPE_SECRET_KEY is missing or is a placeholder in .env")
    print("Please set a valid Test Secret Key (sk_test_...) in .env first.")
    sys.exit(1)

print(f"✅ Using Stripe Key: {stripe.api_key[:12]}...")

def get_or_create_product(name, description=""):
    # Search existing
    resp = stripe.Product.search(query=f"active:'true' AND name:'{name}'", limit=1)
    if resp['data']:
        print(f"   Found existing Product: {name}")
        return resp['data'][0]
    
    print(f"   Creating Product: {name}")
    return stripe.Product.create(name=name, description=description)

def get_or_create_price(product_id, unit_amount, currency="usd", interval=None, lookup_key=None):
    # Search is hard for prices, we'll list and filter
    prices = stripe.Price.list(product=product_id, active=True, limit=100)
    
    # Try to match by properties
    for p in prices.data:
        if p.unit_amount == unit_amount and p.currency == currency:
            if interval:
                if p.recurring and p.recurring.interval == interval:
                    return p
            else:
                if not p.recurring: # One-time
                    return p
    
    print(f"   Creating Price: ${unit_amount/100:.2f} {interval if interval else 'one-time'}")
    
    kwargs = {
        "product": product_id,
        "unit_amount": unit_amount,
        "currency": currency,
    }
    if interval:
        kwargs["recurring"] = {"interval": interval}
    if lookup_key:
        kwargs["lookup_key"] = lookup_key
        
    return stripe.Price.create(**kwargs)

REQUIRED_ITEMS = [
    {
        "env_var": "STRIPE_PRICE_MONTHLY",
        "prod_name": "Pro Subscription (Monthly)",
        "amount": 2900, # $29.00
        "interval": "month"
    },
    {
        "env_var": "STRIPE_PRICE_ANNUAL",
        "prod_name": "Pro Subscription (Annual)",
        "amount": 29000, # $290.00
        "interval": "year"
    },
    {
        "env_var": "STRIPE_PRICE_SIGN",
        "prod_name": "Standard Sign (Generic)",
        "amount": 4500, # $45.00
        "interval": None
    },
    {
        "env_var": "STRIPE_PRICE_SIGN_12X18",
        "prod_name": "Sign 12x18",
        "amount": 3500,
        "interval": None,
        "lookup_key": "sign_12x18"
    },
    {
        "env_var": "STRIPE_PRICE_SIGN_18X24",
        "prod_name": "Sign 18x24",
        "amount": 4500,
        "interval": None,
        "lookup_key": "sign_18x24"
    },
    {
        "env_var": "STRIPE_PRICE_SIGN_24X36",
        "prod_name": "Sign 24x36",
        "amount": 8500,
        "interval": None,
        "lookup_key": "sign_24x36"
    },
    {
        "env_var": "STRIPE_PRICE_SIGN_36X18",
        "prod_name": "Sign 36x18",
        "amount": 6500,
        "interval": None,
        "lookup_key": "sign_36x18"
    },
]

env_lines = []

print("\n--- Bootstrapping Products & Prices ---\n")

for item in REQUIRED_ITEMS:
    prod = get_or_create_product(item["prod_name"])
    price = get_or_create_price(
        prod.id, 
        item["amount"], 
        interval=item.get("interval"),
        lookup_key=item.get("lookup_key")
    )
    env_lines.append(f"{item['env_var']}={price.id}")

print("\n" + "="*60)
print("SUCCESS! Copy the following lines into your .env file:")
print("="*60)
print("\n".join(env_lines))
print("\n" + "="*60)
