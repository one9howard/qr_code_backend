"""
Print Preflight Demo Script.
Generates test PDFs for all sign sizes and runs preflight validation.
"""
import os
import sys
import tempfile
import shutil

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.pdf_generator import generate_pdf_sign
from utils.print_preflight import PreflightError
from constants import SIGN_SIZES

def main():
    print("=" * 60)
    print("Running Print Preflight Demo")
    print("=" * 60)
    
    # Create temp output directory
    out_dir = os.path.join(os.path.dirname(__file__), "..", "instance", "preflight_demo_output")
    if os.path.exists(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    
    print(f"Output directory: {out_dir}")
    print()
    
    results = {}
    
    for size in SIGN_SIZES.keys():
        print(f"Testing size: {size}...")
        try:
            path = generate_pdf_sign(
                address="1234 Print St NW",
                beds=4, baths=3,
                sqft=2500, price="850,000",
                agent_name="Veronica Validation",
                brokerage="Quality Control Realty",
                agent_email="v.valid@example.com",
                agent_phone="555-0199",
                qr_path=None, # Will use fallback
                qr_value="https://example.com/preflight-test",
                sign_size=size,
                sign_color="#0066CC"
            )
            
            # If it succeeded, it passed preflight
            new_path = os.path.join(out_dir, f"pass_{size}.pdf")
            shutil.copy(path, new_path)
            print(f"  [PASS] Generated: {os.path.basename(new_path)}")
            results[size] = "PASS"
            
        except PreflightError as e:
            print(f"  [FAIL] Preflight failed: {e}")
            results[size] = f"FAIL: {e}"
        except Exception as e:
            print(f"  [ERROR] Unexpected error: {e}")
            results[size] = f"ERROR: {e}"
            
    print("-" * 60)
    print("Summary:")
    for size, res in results.items():
        print(f"  {size}: {res}")
    print("-" * 60)
    
    if any("FAIL" in res or "ERROR" in res for res in results.values()):
        print("Some tests FAILED.")
        sys.exit(1)
    else:
        print("All tests PASSED.")
        sys.exit(0)

if __name__ == "__main__":
    main()
