"""
Verify Cleanup Script - Release Gate Checks.

Validates strategy.md invariants:
- PAID_STATUSES used canonically
- No scattered 'paid' literals
- Webhook-only fulfillment
- No PII in logs
- Safe upload keys
"""
import sys
import subprocess

def run(cmd, allow_fail=False):
    print(f"\nRUNNING: {cmd}")
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if res.returncode != 0 and not allow_fail:
        print(f"FAILED: {cmd}")
        print(res.stderr)
        print(res.stdout)
        sys.exit(1)
    print("OUTPUT:")
    print(res.stdout[:1000] if res.stdout else "(no output)")
    return res

print("=== 1. COMPILE CHECK ===")
run("python -m compileall -q .")

print("=== 2. SUCCESS PAGES READ-ONLY ===")
# Should return NOTHING (Exit 1)
res = subprocess.run('findstr /i "process_paid_order" routes\\orders.py routes\\billing.py', shell=True, capture_output=True, text=True)
if res.returncode == 0 and "process_paid_order" in res.stdout:
    print("FAILURE: Success pages still contain process_paid_order!")
    sys.exit(1)
print("PASS: Success pages are read-only")

print("=== 3. CANONICAL PAID_STATUSES ===")
# Dashboard should use PAID_STATUSES, not literal 'paid'
res = subprocess.run('findstr /i "status = \'paid\'" routes\\dashboard.py', shell=True, capture_output=True, text=True)
if res.returncode == 0:
    print("FAILURE: Found literal 'paid' in dashboard.py!")
    sys.exit(1)
run('findstr "PAID_STATUSES" routes\\dashboard.py')
print("PASS: Dashboard uses PAID_STATUSES")

print("=== 4. NO PII IN LOGS ===")
res = subprocess.run('findstr /i "from {buyer_email}" routes\\leads.py', shell=True, capture_output=True, text=True)
if res.returncode == 0:
    print("FAILURE: PII (buyer_email) found in leads.py logger!")
    sys.exit(1)
print("PASS: No PII in leads.py logs")

print("=== 5. SAFE UPLOAD KEYS ===")
res = subprocess.run('findstr /i "uploads/brands" routes\\smart_signs.py', shell=True, capture_output=True, text=True)
if res.returncode == 0:
    print("FAILURE: Old 'uploads/brands' paths found in smart_signs.py!")
    sys.exit(1)
run('findstr "uploads/smartsign" routes\\smart_signs.py')
print("PASS: Safe upload keys in smart_signs.py")

print("=== 6. SIGN_ASSETS CREATION IN ORDERS SERVICE ===")
res = subprocess.run('findstr /i "INSERT INTO sign_assets" routes\\smart_signs.py routes\\smart_riser.py routes\\webhook.py', shell=True, capture_output=True, text=True)
if res.returncode == 0:
    print("FAILURE: sign_assets INSERT found in checkout routes!")
    sys.exit(1)
run('findstr "INSERT INTO sign_assets" services\\orders.py')
print("PASS: sign_assets creation in services/orders.py only")

print("\n=== ALL CLEANUP CHECKS PASSED ===")
