#!/bin/bash
set -e

echo "1. Bytecode Compilation Check..."
python -m compileall -q .

echo "2. Release Cleanliness Check..."
python scripts/check_release_clean.py

echo "3. Security Sanity Check..."
python scripts/security_sanity_check.py

echo "4. Import Safety Check..."
python scripts/verify_import_safety.py

echo "5. Running Tests (Fast)..."
python -m pytest -q

echo "6. Targeted Phase Tests..."
# Running focused tests
python -m pytest -q tests/test_print_jobs.py tests/test_smart_sign_pricing.py tests/test_smart_sign_checkout.py


echo "All checks passed!"
