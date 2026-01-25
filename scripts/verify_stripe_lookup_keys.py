#!/usr/bin/env python3
"""Verify Stripe lookup-key pricing configuration (Phase 6)

Runs a strict warm-cache over all required lookup keys defined in services/print_catalog.py.
This confirms:
- Each lookup key exists
- Price is active
- Product is active

Usage:
  python scripts/verify_stripe_lookup_keys.py
"""

import os
import stripe
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))

from services.stripe_client import init_stripe

class AppMock:
    config = {
        'STRIPE_SECRET_KEY': os.getenv('STRIPE_SECRET_KEY'),
        'APP_STAGE': os.getenv('APP_STAGE', 'dev')
    }
    
init_stripe(AppMock)

from services.print_catalog import get_all_required_lookup_keys
from services.stripe_price_resolver import warm_cache

keys = get_all_required_lookup_keys()
print(f"Verifying {len(keys)} lookup keys...")

warm_cache(keys)
print("OK: All required lookup keys resolved and cached.")
