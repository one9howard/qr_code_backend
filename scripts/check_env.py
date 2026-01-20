import os

print("--- Environment Variable Debugger ---")
print(f"FLASK_ENV: {os.environ.get('FLASK_ENV')}")
print(f"APP_STAGE: {os.environ.get('APP_STAGE')}")
print("\n--- STRIPE Variables Found ---")
keys = [k for k in os.environ.keys() if k.startswith("STRIPE_")]
for key in sorted(keys):
    val = os.environ[key]
    if len(val) > 8:
        masked = val[:4] + "..." + val[-4:]
    else:
        masked = "***"
    print(f"{key}: {masked}")

print("\n--- Checking Specific Failure ---")
print(f"STRIPE_PRICE_ANNUAL is present? {'YES' if 'STRIPE_PRICE_ANNUAL' in os.environ else 'NO'}")
if 'STRIPE_PRICE_ANNUAL' not in os.environ:
    print("  -> CAUSE: This variable is missing from the container environment.")
    print("  -> CHECK 1: Typo in .env? (Check for trailing spaces 'KEY = VAL')")
    print("  -> CHECK 2: Did you restart docker compose? (docker compose restart)")
else:
    print(f"  -> VALUE SEEN: {os.environ['STRIPE_PRICE_ANNUAL']}")
    if os.environ['STRIPE_PRICE_ANNUAL'] == "price_annual_id":
        print("  -> ERROR: Value is 'price_annual_id' which suggests it fell back to default in config.py!")
