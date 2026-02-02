import os
import sys

# Ensure project root is in path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.pdf_smartsign import generate_smartsign_pdf
from services.print_catalog import SMART_SIGN_LAYOUTS
from services.printing.layout_utils import register_fonts

def run_samples():
    print(">>> 1. Registering Fonts...")
    try:
        register_fonts()
        print("    [OK] Fonts registered.")
    except Exception as e:
        print(f"    [FAIL] Font registration error: {e}")
        sys.exit(1)

    print(f">>> 2. Generating Samples for Layouts: {SMART_SIGN_LAYOUTS}")
    
    # Fake Asset Data (Phase 2 Compatible)
    mock_assets = {
        'default': {
            'code': 'TESTCODE123',
            'print_size': '18x24',
            'agent_name': 'Sarah Thomas',
            'agent_phone': '123-456-7890',
            'status_text': 'FOR SALE',
            'cta_key': 'scan_for_details',
            'state': 'CA',
            'license_number': '1234567',
            'show_license_number': True,
            # Keys would need to exist in storage, but we can test w/o images or mock them
            # For now, let's assume no images or just text rendering
        },
        'brand': {
             'code': 'BRAND123',
             'print_size': '24x36',
             'agent_name': 'James Luxury',
             'agent_phone': '555-000-9999',
             'status_text': 'OPEN HOUSE',
            'cta_key': 'scan_to_schedule',
             'state': 'NY',
             'license_number': '999999',
        }
    }
    
    output_dir = "pdfs/samples"
    os.makedirs(output_dir, exist_ok=True)
    
    for layout in SMART_SIGN_LAYOUTS:
        print(f"    Generating {layout}...")
        
        # Pick standard mock
        asset = mock_assets['default'].copy()
        asset['layout_id'] = layout
        
        try:
            # We bypass storage for images by not providing keys if we don't have them
            # Or use a local file if needed.
            # For this test, text rendering is the critical part to verify layout logic.
            
            key = generate_smartsign_pdf(asset, order_id=999, user_id=1, override_base_url="https://staging.insitesigns.com")
            
            # The generate function returns a key, but it writes to Storage interface.
            # If using LocalStorage (default in dev), it puts it in 'storage_local/pdfs/...'
            # We want to verify it exists.
            
            print(f"    -> Generated Key: {key}")
            
            # If local storage, verify file
            from utils.storage import get_storage
            s = get_storage()
            if s.exists(key):
                 data = s.get_file(key)
                 if hasattr(data, 'read'):
                     data = data.read()
                 size = len(data)
                 print(f"       [OK] File exists, size: {size} bytes")
                 
                 # Optional: Copy to samples dir for easy viewing
                 # (If s is LocalStorage, we can just copy)
                 # Simulating copy:
                 out_path = os.path.join(output_dir, f"sample_{layout}.pdf")
                 with open(out_path, "wb") as f:
                     f.write(data)
                 print(f"       Saved copy to: {out_path}")
                 
            else:
                 print("       [FAIL] Storage key not found.")
                 
        except Exception as e:
            print(f"       [ERROR] {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    run_samples()
