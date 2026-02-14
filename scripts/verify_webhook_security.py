#!/usr/bin/env python3
"""Verify Stripe webhook security behavior.

Defaults to localhost and can be overridden via:
  - env BASE_URL
  - CLI: --base-url http://host:port

Examples:
  python scripts/verify_webhook_security.py
  BASE_URL=http://localhost:8080 python scripts/verify_webhook_security.py
  python scripts/verify_webhook_security.py --base-url http://localhost:8080
"""

import os
import argparse
import requests

def test_bypass_attempt(webhook_url: str) -> None:
    """Attempt to use the removed bypass mechanism. Should FAIL (400 Invalid signature)."""
    print(f"Testing bypass attempt on {webhook_url}...")
    payload = {
        "id": "evt_test_bypass",
        "object": "event",
        "type": "payment_intent.succeeded",
    }
    try:
        r = requests.post(f"{webhook_url}?dev_bypass=true", json=payload, timeout=5)
        if r.status_code == 400 and "Invalid signature" in r.text:
            print("✅ SUCCESS: Bypass attempt rejected with 400 Invalid signature.")
        else:
            print(f"❌ FAILURE: Unexpected response. Status: {r.status_code}, Body: {r.text}")
    except Exception as e:
        print(f"❌ ERROR: Request failed: {e}")

def test_no_signature(webhook_url: str) -> None:
    """Attempt to post without any signature. Should FAIL (400)."""
    print(f"Testing no-signature attempt on {webhook_url}...")
    payload = {"id": "evt_test_nosig", "object": "event"}
    try:
        r = requests.post(webhook_url, json=payload, timeout=5)
        if r.status_code == 400:
            print("✅ SUCCESS: No-signature attempt rejected with 400.")
        else:
            print(f"❌ FAILURE: Unexpected response. Status: {r.status_code}, Body: {r.text}")
    except Exception as e:
        print(f"❌ ERROR: Request failed: {e}")

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default=os.environ.get("BASE_URL", "http://localhost:8080"),
                    help="Base URL of the running app (default: env BASE_URL or http://localhost:8080)")
    args = ap.parse_args()

    base = args.base_url.rstrip("/")
    webhook_url = f"{base}/stripe/webhook"

    print("--- Verifying Webhook Security Fix ---")
    test_bypass_attempt(webhook_url)
    test_no_signature(webhook_url)

if __name__ == "__main__":
    main()
