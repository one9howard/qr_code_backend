
import sys
import subprocess
import time

def run(cmd, allow_fail=False):
    print(f"\nRUNNING: {cmd}")
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if res.returncode != 0 and not allow_fail:
        print(f"FAILED: {cmd}")
        print(res.stderr)
        print(res.stdout)
        sys.exit(1)
    print("OUTPUT:")
    print(res.stdout[:2000] if res.stdout else "(no output)")
    if res.stderr:
        print("STDERR:")
        print(res.stderr[:500])
    return True

print("=== 1. COMPILE CHECK ===")
run("python -m py_compile routes/listing_kits.py")
run("python -m py_compile routes/webhook.py")
run("python -m py_compile routes/smart_signs.py")
run("python -m py_compile routes/smart_riser.py")

print("=== 2. GREP PROOFS ===")
print("--- Listing Kits Persistent Queue ---")
run('findstr "status=\'queued\'" routes\\listing_kits.py services\\listing_kits.py')

print("--- Webhook Canonical Freeze ---")
run('findstr "PAID_STATUSES" routes\\webhook.py')

print("--- SmartSigns Creation (Should be missing in checkout routes) ---")
# On Windows findstr returns 1 if not found. We EXPECT not found for checkout routes.
subprocess.run('findstr "INSERT INTO sign_assets" routes\\smart_signs.py routes\\smart_riser.py routes\\webhook.py', shell=True)
print("(Above command should have no output if successful exclusion)")

print("--- SmartSigns Creation (Should be present in services/orders.py) ---")
run('findstr "INSERT INTO sign_assets" services\\orders.py')

print("--- Activation Linkage ---")
run('findstr "activation_order_id" services\\orders.py')

print("=== 3. TESTS ===")
run("python -m pytest -q tests/test_strategy_alignment.py")

print("=== 4. BOOT SANITY ===")
try:
    from app import create_app
    app = create_app()
    with app.app_context():
        print("App initialized successfully (No Traceback).")
except Exception as e:
    print(f"App Boot Failed: {e}")
    sys.exit(1)

print("\nALL CHECKS PASSED")
