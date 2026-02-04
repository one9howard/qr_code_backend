
import requests
import time

BASE_URL = "http://192.168.1.186:5000"
WEBHOOK_URL = f"{BASE_URL}/stripe/webhook"

def test_bypass_attempt():
    """Attempt to use the removed bypass mechanism. Should FAIL (400)."""
    print(f"Testing bypass attempt on {WEBHOOK_URL}...")
    
    # Payload that would be valid JSON
    payload = {
        "id": "evt_test_bypass",
        "object": "event",
        "type": "payment_intent.succeeded"
    }
    
    # Try using the query param bypass
    try:
        response = requests.post(f"{WEBHOOK_URL}?dev_bypass=true", json=payload, timeout=5)
        
        if response.status_code == 400 and "Invalid signature" in response.text:
            print("✅ SUCCESS: Bypass attempt rejected with 400 Invalid signature.")
        else:
            print(f"❌ FAILURE: Unexpected response. Status: {response.status_code}, Body: {response.text}")
    except Exception as e:
        print(f"❌ ERROR: Request failed: {e}")

def test_no_signature():
    """Attempt to post without any signature. Should FAIL (400)."""
    print(f"Testing no-signature attempt on {WEBHOOK_URL}...")
    
    payload = {"id": "evt_test_nosig", "object": "event"}
    
    try:
        response = requests.post(WEBHOOK_URL, json=payload, timeout=5)
        
        if response.status_code == 400:
             print("✅ SUCCESS: No-signature attempt rejected with 400.")
        else:
            print(f"❌ FAILURE: Unexpected response. Status: {response.status_code}")
    except Exception as e:
         print(f"❌ ERROR: Request failed: {e}")

if __name__ == "__main__":
    print("--- Verifying Webhook Security Fix ---")
    test_bypass_attempt()
    test_no_signature()
