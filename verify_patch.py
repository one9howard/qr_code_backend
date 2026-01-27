
import sys
import subprocess
import time

def run(cmd):
    print(f"RUNNING: {cmd}")
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"FAILED: {cmd}")
        print(res.stderr)
        print(res.stdout)
        sys.exit(1)
    print("OK")
    print(res.stdout[:500]) # truncated
    return True

print("=== BLOCKER 1: SYNTAX ===")
run("python -m py_compile routes/webhook.py")
run("python -m py_compile services/gating.py")
run("python -m py_compile scripts/async_worker.py")

print("=== BLOCKER 2: SMARTSIGN STRICT ===")
# Grep should NOT find smart-signs/create (return code 1 means not found, which is good for grep search of forbidden string)
# But standard grep returns 1 if not found. We want NOT found.
res = subprocess.run('grep -R "smart-signs/create" .', shell=True, capture_output=True)
if res.returncode == 0:
    print("FAILED: Found smart-signs/create!")
    sys.exit(1)
else:
    print("OK: No manual creation route found.")

print("=== BLOCKER 3: ASYNC PAYLOAD ===")
# Verify payload parsing code exists
run('grep "payload.get" scripts/async_worker.py') 

print("=== BLOCKER 4: KIT STATUS ===")
# Verify queued status usage
run('grep "queued" services/listing_kits.py')

print("=== TESTS ===")
run("python -m pytest tests/test_strategy_alignment.py")

print("=== BOOT CHECK ===")
# We can't easily start the server here without blocking, but we can try to import app
try:
    from app import create_app
    app = create_app()
    with app.app_context():
        print("App initialized successfully.")
except Exception as e:
    print(f"App Boot Failed: {e}")
    sys.exit(1)

print("ALL CHECKS PASSED")
