import requests
import re
import sys

BASE_URL = "https://staging.insitesigns.com"
LOGIN_URL = f"{BASE_URL}/login"
DASHBOARD_URL = f"{BASE_URL}/dashboard"

EMAIL = "test@email.com"
PASSWORD = "test"

def get_csrf_token(text):
    # Match <input type="hidden" name="csrf_token" value="...">
    # Be flexible with quotes and attribute order
    match = re.search(r'name=["\']csrf_token["\'][^>]*value=["\']([^"\']+)["\']', text)
    if match:
        return match.group(1)
    # Try reverse order
    match = re.search(r'value=["\']([^"\']+)["\'][^>]*name=["\']csrf_token["\']', text)
    if match:
        return match.group(1)
    return None

def main():
    s = requests.Session()
    s.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})

    # 1. Get Login Page for CSRF
    print(f"Fetching Login Page...")
    try:
        resp = s.get(LOGIN_URL)
        resp.raise_for_status()
    except Exception as e:
        print(f"Failed to fetch login page: {e}")
        sys.exit(1)
        
    csrf_token = get_csrf_token(resp.text)
    
    if not csrf_token:
        print("Warning: No CSRF token found on login page. Attempting login without it.")
    else:
        print(f"Login CSRF Token found: {csrf_token[:10]}...")

    # 2. Login
    print(f"Logging in as {EMAIL}...")
    payload = {"email": EMAIL, "password": PASSWORD}
    if csrf_token:
        payload["csrf_token"] = csrf_token
        
    try:
        resp = s.post(LOGIN_URL, data=payload)
        resp.raise_for_status()
    except Exception as e:
        print(f"Login failed: {e}")
        sys.exit(1)
        
    if "dashboard" not in resp.url and "verify" not in resp.url:
         print(f"Login might have failed or redirected elsewhere: {resp.url}")

    # 3. Get Dashboard
    print("Fetching dashboard...")
    resp = s.get(DASHBOARD_URL)
    
    # Get a fresh CSRF token from the dashboard
    csrf_token = get_csrf_token(resp.text)
    print(f"Dashboard CSRF Token: {csrf_token[:10] if csrf_token else 'None'}...")

    # 4. Find Property IDs
    # Pattern: href="/dashboard/edit/(\d+)"
    property_ids = set(re.findall(r'/dashboard/edit/(\d+)', resp.text))

    if not property_ids:
        print("No properties found to delete.")
        sys.exit(0)
        
    print(f"Found properties: {property_ids}")
    
    # 5. Delete Properties
    for pid in property_ids:
        delete_url = f"{BASE_URL}/dashboard/delete/{pid}"
        print(f"Deleting property {pid} at {delete_url}...")
        try:
            # The route is POST
            # Must include CSRF token
            del_payload = {}
            if csrf_token:
                del_payload["csrf_token"] = csrf_token
            
            # Important: Headers for CSRF referer check
            headers = {"Referer": DASHBOARD_URL}
                
            resp = s.post(delete_url, data=del_payload, headers=headers)
            
            if resp.status_code == 200 or resp.status_code == 302:
                print(f"Successfully deleted property {pid}")
            else:
                print(f"Failed to delete property {pid}: Status {resp.status_code}")
        except Exception as e:
            print(f"Error deleting property {pid}: {e}")

if __name__ == "__main__":
    main()
