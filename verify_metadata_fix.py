
import sys
import subprocess

def run(cmd):
    print(f"\nRUNNING: {cmd}")
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"FAILED: {cmd}")
        print(res.stderr)
        print(res.stdout)
        sys.exit(1)
    print("OUTPUT:")
    print(res.stdout[:500])
    return True

print("=== COMPILE CHECK ===")
run("python -m py_compile routes/smart_signs.py")
run("python -m py_compile routes/smart_riser.py")
run("python -m py_compile routes/webhook.py")

print("=== GREP CHECK: Conditional Metadata ===")
run('findstr "if.*asset_id.*is.*not.*None" routes\\smart_signs.py')
run('findstr "if.*asset_id.*is.*not.*None" routes\\smart_riser.py')

print("=== GREP CHECK: Parsing Helper Usage ===")
run('findstr "_parse_sign_asset_id" routes\\webhook.py')

print("=== TESTS ===")
run("python -m pytest tests/test_fix_metadata.py")

print("\nALL CHECKS PASSED")
