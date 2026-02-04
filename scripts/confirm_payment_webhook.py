import requests
import re
import sys
import json
import time

BASE_URL = "http://192.168.1.186:5000"
EMAIL = "test3@email.com"
PASSWORD = "test"
SESSION = requests.Session()

def log(msg, type="INFO"):
    print(f"[{type}] {msg}")

def login():
    log(f"Logging in as {EMAIL}...")
    try:
        resp = SESSION.get(f"{BASE_URL}/login")
        csrf = re.search(r'name="csrf_token" value="(.+?)"', resp.text).group(1)
        
        login_payload = {
            'email': EMAIL,
            'password': PASSWORD,
            'csrf_token': csrf
        }
        res = SESSION.post(f"{BASE_URL}/login", data=login_payload)
        if "Dashboard" in res.text or "/dashboard" in res.url:
            log("Login success!")
            return True
        else:
            log("Login failed.", "ERROR")
            return False
    except Exception as e:
        log(f"Login exception: {e}", "ERROR")
        return False

def get_pending_orders():
    log("Scanning dashboard for pending orders...")
    try:
        resp = SESSION.get(f"{BASE_URL}/dashboard")
        # Look for "Resume Setup" links: /smart-signs/order/(\d+)/preview
        # Note: In Step 824 route is @smart_signs_bp.route('/order/<int:order_id>/preview')
        # URL prefix is /smart-signs assigned in app register_blueprint?
        # Assuming it is `/smart-signs/order/<id>/preview`
        
        # Regex to find all order IDs in resume links
        # href="/smart-signs/order/20/preview"
        ids = re.findall(r'href="/smart-signs/order/(\d+)/preview"', resp.text)
        
        # Also check just in case mount point is different or my regex is too strict
        if not ids:
             # Try broader
             ids = re.findall(r'/order/(\d+)/preview', resp.text)
        
        unique_ids = list(set(ids))
        log(f"Found {len(unique_ids)} pending orders: {unique_ids}")
        return unique_ids
    except Exception as e:
        log(f"Scrape failed: {e}", "ERROR")
        return []

def send_webhook(order_id):
    log(f"Sending webhook for Order {order_id}...")
    
    # Construct a minimal valid checkout.session.completed event
    # We need: id, type, data.object.metadata.order_id, payment_status='paid'
    
    payload = {
        "id": f"evt_dev_confirm_{order_id}",
        "object": "event",
        "api_version": "2020-08-27",
        "created": int(time.time()),
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": f"cs_dev_mock_{order_id}",
                "object": "checkout.session",
                "payment_status": "paid",
                "status": "complete",
                "mode": "payment",
                "amount_total": 2400,
                "currency": "usd",
                "customer": "cus_dev_mock", # Mock customer
                "customer_details": {
                    "email": EMAIL,
                    "name": "Test User"
                },
                "metadata": {
                    "order_id": str(order_id),
                    "purpose": "smart_sign",
                    "sign_asset_id": "null" # Simulate new asset logic
                }
            }
        }
    }
    
    headers = {
        "Content-Type": "application/json",
        "X-Dev-Bypass-Signature": "dev-bypass"
    }
    
    try:
        resp = requests.post(
            f"{BASE_URL}/stripe/webhook?dev_bypass=true",
            json=payload,
            headers=headers
        )
        if resp.status_code == 200:
            log(f"Webhook sent successfully for Order {order_id}. Resp: {resp.text}")
            return True
        else:
            log(f"Webhook failed for {order_id}: {resp.status_code} - {resp.text}", "ERROR")
            return False
            
    except Exception as e:
        log(f"Webhook exception: {e}", "ERROR")
        return False

# MAIN
if __name__ == "__main__":
    if not login():
        sys.exit(1)
        
    orders = get_pending_orders()
    if not orders:
        log("No pending orders to process.")
        sys.exit(0)
        
    for oid in orders:
        send_webhook(oid)
        time.sleep(1)
        
    log("All webhooks sent. Checking dashboard again...")
    time.sleep(2)
    
    # Verify
    pending_now = get_pending_orders()
    if not pending_now:
        log("SUCCESS: All pending orders cleared!")
    else:
        log(f"WARNING: {len(pending_now)} orders still pending: {pending_now}")
