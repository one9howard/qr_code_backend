
import sys
import subprocess

def run(cmd):
    print(f"\nRUNNING: {cmd}")
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"FAILED: {cmd}")
        print(res.stderr)
        # sys.exit(1) # Continue to show other checks
    else:
        print("OK")
    return res

print("=== TESTS ===")
run("python -m pytest tests/test_analytics.py")

print("\n=== GREP CHECKS ===")
run('findstr "Total Scans" templates\\dashboard.html')
run('findstr "property_views" services\\analytics.py')
run('findstr "qr_scans" services\\analytics.py')
run('findstr "cta_click" services\\analytics.py')

print("\n=== ROUTE CHECK ===")
run('findstr "property_analytics" routes\\dashboard.py')
