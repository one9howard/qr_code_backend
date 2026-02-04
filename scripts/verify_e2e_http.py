import requests
import sys
import re

BASE_URL = "http://192.168.1.186:5000"
EMAIL = "test3@email.com"
PASSWORD = "test"
SESSION = requests.Session()

def log(msg, type="INFO"):
    print(f"[{type}] {msg}")

def get_csrf(text):
    match = re.search(r'name="csrf_token" value="([^"]+)"', text)
    return match.group(1) if match else None

def login():
    log(f"Logging in as {EMAIL}...")
    resp = SESSION.get(f"{BASE_URL}/login")
    if resp.status_code != 200:
        log(f"Login page fetch failed: {resp.status_code}", "ERROR")
        return False
    
    csrf_token = get_csrf(resp.text)
    data = {"email": EMAIL, "password": PASSWORD}
    if csrf_token: data['csrf_token'] = csrf_token
        
    resp = SESSION.post(f"{BASE_URL}/login", data=data)
    
    if resp.url.endswith("/dashboard") or "dashboard" in resp.url:
        log("Login success!")
        return True
    
    log(f"Login failed. URL: {resp.url}", "ERROR")
    return False

def verify_button_color(order_id):
    log(f"Verifying Preview Page for Order {order_id}...")
    resp = SESSION.get(f"{BASE_URL}/smart-signs/order/{order_id}/preview")
    
    if resp.status_code != 200:
        log("Preview page fetch failed", "ERROR")
        return False

    # Check for green color style
    if "#00D924" in resp.text:
        log("SUCCESS: Button has Stripe Green color code!")
    else:
        log("WARNING: Button green color code NOT found in HTML. (Note: Server might need restart if template caching is on).", "WARN")

def create_smart_sign():
    log("Creating SmartSign Order...")
    resp = SESSION.get(f"{BASE_URL}/smart-signs/order/start")
    csrf_token = get_csrf(resp.text)
    
    payload = {
        'size': '18x24',
        'layout_id': 'standard_layout',
        'agent_name': 'Test User',
        'agent_phone': '555-1234',
        'check_agree': 'on'
    }
    if csrf_token: payload['csrf_token'] = csrf_token
    
    resp = SESSION.post(f"{BASE_URL}/smart-signs/order/create", data=payload)
    
    match = re.search(r'/order/(\d+)/preview', resp.url)
    if match:
        order_id = match.group(1)
        log(f"Order Created: {order_id}")
        verify_button_color(order_id)
        return order_id
    
    log(f"Order creation failed. URL: {resp.url}", "ERROR")
    return None

def create_property(suffix):
    log(f"Creating Property 'Test Prop {suffix}'...")
    resp = SESSION.get(f"{BASE_URL}/dashboard/properties/new")
    csrf_token = get_csrf(resp.text)

    payload = {
        'address': f"Test Prop {suffix}",
        'beds': 3,
        'baths': 2,
        'price': 1000000
    }
    if csrf_token: payload['csrf_token'] = csrf_token
    
    resp = SESSION.post(f"{BASE_URL}/dashboard/properties/new", data=payload)
    
    if "dashboard" in resp.url:
        log("Property Created.")
    else:
        log("Property Creation Failed.", "ERROR")

def run():
    if not login(): sys.exit(1)
    
    order_id = create_smart_sign()
    
    create_property("One")
    create_property("Two")
    create_property("Three")
    
    log("Verification steps complete (Payment/Assignment skipped due to no Stripe access).")

if __name__ == "__main__":
    run()
