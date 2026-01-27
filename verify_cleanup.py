
import sys
import subprocess

def run(cmd):
    print(f"\nRUNNING: {cmd}")
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if res.returncode != 0:
        # Grep returns 1 if NOT found, which might be good for negative checks
        # But compile should be 0
        if "py_compile" in cmd:
            print(f"FAILED: {cmd}")
            print(res.stderr)
            sys.exit(1)
    print("OUTPUT (First 500 chars):")
    print(res.stdout[:500])
    return res

print("=== COMPILE CHECK ===")
run("python -m py_compile routes/smart_riser.py")

print("=== GREP CHECK: SmartRiser order_type ===")
# Should return NOTHING (Exit 1)
res = run('findstr "order_type.*smart_sign" routes\\smart_riser.py')
if res.returncode == 0 and "smart_sign" in res.stdout:
    print("FAILURE: Found 'smart_sign' in smart_riser.py order_type logic!")
    # sys.exit(1) # Don't exit yet, show all output

print("=== GREP CHECK: SmartRiser Metadata ===")
run('findstr "metadata.*order_type" routes\\smart_riser.py')

print("=== GREP CHECK: Admin Orders Drift ===")
# Should return NOTHING (Exit 1)
res = run('findstr "order.status == \'paid\'" templates\\admin_orders.html')
if res.returncode == 0 and "order.status == 'paid'" in res.stdout:
     print("FAILURE: Found literal 'paid' check in admin_orders.html!")

print("=== TESTS ===")
run("python -m pytest tests/test_fix_cleanup.py")

print("\nBOOT SANITY (Simulated)")
try:
    from app import create_app
    print("App Import OK")
except Exception as e:
    print(f"App Import Failed: {e}")
