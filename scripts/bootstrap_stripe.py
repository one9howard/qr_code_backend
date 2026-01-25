#!/usr/bin/env python3
"""Bootstrap Stripe Products & Prices (Phase 6)

What this script does:
- Ensures the Pro subscription prices exist (MONTHLY/ANNUAL) and prints .env lines for those.
- Ensures all *print* products/prices exist with the required *lookup_key* values.
  Print prices are NOT written to .env; the app resolves them via lookup keys at runtime.

Requirements:
- STRIPE_SECRET_KEY must be set in .env (test mode key recommended)

Usage:
  python scripts/bootstrap_stripe.py

NOTE:
- The app will refuse to start in non-test mode if required lookup keys are missing or inactive.
- The resolver requires both Price.active == True and Product.active == True.
"""

import os
import sys
import stripe
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))

# Centralized Init
from services.stripe_client import init_stripe

class AppMock:
    config = {
        'STRIPE_SECRET_KEY': os.getenv('STRIPE_SECRET_KEY'),
        'APP_STAGE': os.getenv('APP_STAGE', 'dev')
    }

init_stripe(AppMock)

print(f"Using Stripe key: {stripe.api_key[:12]}...")


def _product_by_name(name: str):
    # Search active first
    resp = stripe.Product.search(query=f"active:'true' AND name:'{name}'", limit=1)
    if resp.data:
        return resp.data[0]

    # If not found active, try any status by listing a few matches
    # Stripe search doesn't support active:false directly in all accounts; keep it simple:
    resp2 = stripe.Product.search(query=f"name:'{name}'", limit=5)
    for p in resp2.data:
        if p.name == name:
            # If inactive, reactivate it
            if hasattr(p, 'active') and not p.active:
                print(f"Re-activating Product: {name}")
                return stripe.Product.modify(p.id, active=True)
            return p
    return None


def get_or_create_product(name: str, description: str = ""):
    existing = _product_by_name(name)
    if existing:
        return existing
    print(f"Creating Product: {name}")
    return stripe.Product.create(name=name, description=description, active=True)


def get_or_create_price(*, product_id: str, unit_amount: int, currency: str = "usd", interval: str | None = None, lookup_key: str | None = None):
    # If lookup_key specified, try to find an existing active price with that key first.
    if lookup_key:
        resp = stripe.Price.list(lookup_keys=[lookup_key], active=True, limit=100)
        for pr in resp.data:
            # Ensure it's for our product
            if pr.product == product_id:
                return pr

    # Otherwise, list prices for the product and match by amount/interval
    prices = stripe.Price.list(product=product_id, active=True, limit=100)
    for p in prices.data:
        if p.unit_amount == unit_amount and p.currency == currency:
            if interval:
                if p.recurring and p.recurring.interval == interval:
                    return p
            else:
                if not p.recurring:
                    return p

    print(f"Creating Price: product={product_id} amount=${unit_amount/100:.2f} {('interval='+interval) if interval else 'one-time'} lookup_key={lookup_key}")
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


# --- Subscription prices (written to .env) ---
SUBSCRIPTION_ITEMS = [
    {
        "env_var": "STRIPE_PRICE_MONTHLY",
        "name": "Pro Subscription (Monthly)",
        "amount": 2900,
        "interval": "month",
    },
    {
        "env_var": "STRIPE_PRICE_ANNUAL",
        "name": "Pro Subscription (Annual)",
        "amount": 29000,
        "interval": "year",
    },
]

# --- Print catalog (lookup keys only, not written to .env) ---
PRINT_ITEMS = [
    # SmartSign (Aluminum only)
    ("SmartSign Print 18x24",  "smart_sign_print_18x24"),
    ("SmartSign Print 24x36",  "smart_sign_print_24x36"),
    ("SmartSign Print 36x24",  "smart_sign_print_36x24"),

    # Listing Sign - Coroplast
    ("Listing Sign Coroplast 12x18", "listing_sign_coroplast_12x18"),
    ("Listing Sign Coroplast 18x24", "listing_sign_coroplast_18x24"),
    ("Listing Sign Coroplast 24x36", "listing_sign_coroplast_24x36"),

    # Listing Sign - Aluminum
    ("Listing Sign Aluminum 18x24", "listing_sign_aluminum_18x24"),
    ("Listing Sign Aluminum 24x36", "listing_sign_aluminum_24x36"),
    ("Listing Sign Aluminum 36x24", "listing_sign_aluminum_36x24"),

    # SmartRiser (Aluminum)
    ("SmartRiser 6x24", "smart_riser_6x24"),
    ("SmartRiser 6x36", "smart_riser_6x36"),
]

# NOTE: amounts are placeholders; set your desired pricing in Stripe directly if needed.
DEFAULT_PRINT_AMOUNT_CENTS = 6900

print("\n--- Ensuring Subscription Products/Prices ---")
env_lines = []
for item in SUBSCRIPTION_ITEMS:
    prod = get_or_create_product(item["name"], description="")
    price = get_or_create_price(product_id=prod.id, unit_amount=item["amount"], interval=item["interval"], lookup_key=None)
    env_lines.append(f"{item['env_var']}={price.id}")
    print(f"OK: {item['name']} -> {price.id}")

print("\n--- Ensuring Print Products/Prices (lookup keys) ---")
created = 0
for name, key in PRINT_ITEMS:
    prod = get_or_create_product(name, description="Print product")
    price = get_or_create_price(product_id=prod.id, unit_amount=DEFAULT_PRINT_AMOUNT_CENTS, interval=None, lookup_key=key)
    # Ensure product is active
    if hasattr(prod, 'active') and not prod.active:
        stripe.Product.modify(prod.id, active=True)
    # Ensure price is active
    if hasattr(price, 'active') and not price.active:
        stripe.Price.modify(price.id, active=True)
    print(f"OK: {key} -> {price.id} (product={prod.id})")
    created += 1

print("\n" + "="*70)
print("Copy these subscription lines into your .env (prints use lookup keys only):")
print("="*70)
print("\n".join(env_lines))
print("="*70)
print(f"Verified/created {created} print prices with lookup keys.")
