import os
import sys
import logging

# Setup path to run from root
sys.path.append(os.getcwd())

from services.pdf_smartsign import generate_smartsign_pdf
from utils.storage import get_storage

# Mock Asset Data
MOCK_ASSET = {
    'id': 'test_asset',
    'code': 'TESTCODE123',
    'agent_name': 'Jennifer Lawrence',
    'agent_phone': '555-0199',
    'brokerage': 'Luxury Real Estate',
    'status_text': 'JUST LISTED',
    # 'cta_key': 'scan_for_photos', # Commented out to test defaults (e.g. "Scan for Details")
    'banner_color_id': 'navy',
    # 'headshot_key': ... (will fail gracefully if missing, which is fine for layout test)
}

NEW_LAYOUTS = [
    'smart_v2_modern_split',
    'smart_v2_elegant_serif',
    'smart_v2_bold_frame'
]

SIZES = ['18x24', '24x36']

def run_verification():
    print("Verifying New SmartSign Layouts...")
    storage = get_storage()
    
    failures = []
    
    for layout in NEW_LAYOUTS:
        for size in SIZES:
            print(f"  Testing {layout} [{size}]...")
            try:
                asset = MOCK_ASSET.copy()
                asset['layout_id'] = layout
                asset['print_size'] = size
                
                # Generate
                key = generate_smartsign_pdf(asset, order_id='TEST_LAYOUTS', override_base_url='https://example.com')
                
                # Verify file exists in storage (local)
                if storage.exists(key):
                    print(f"    [OK] Generated: {key}")
                else:
                    print(f"    [FAIL] File not found after generation: {key}")
                    failures.append(f"{layout} {size}")
                    
            except Exception as e:
                print(f"    [CRASH] {layout} {size}: {e}")
                import traceback
                traceback.print_exc()
                failures.append(f"{layout} {size}")

    if failures:
        print(f"\n❌ Failures: {failures}")
        sys.exit(1)
    else:
        print("\n✅ All layouts generated successfully.")

if __name__ == "__main__":
    run_verification()
