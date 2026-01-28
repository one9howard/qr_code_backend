
import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

from services.pdf_smartsign import generate_smartsign_pdf
from utils.pdf_preview import render_pdf_to_web_preview
from utils.storage import get_storage
from constants import SIGN_SIZES

# Worst Case Data
WORST_CASE_ASSET = {
    'code': 'ABC-1234',
    'brand_name': 'Alexandria Catherine Van Der Westhuizen', # Very Long Name
    'phone': '555-0199 | 555-0100', # Multiple phones?
    'email': 'alexandria.vanderwesthuizen.longemailaddress@gmail.com', # Very long email
    'brokerage_name': 'Sotheby’s International Realty – Northern California Peninsula', # Long brokerage
    'banner_color_id': 'navy',
    'cta_key': 'scan_for_details',
    'include_logo': True,
    'logo_key': 'test/placeholder_logo.png', # Need to ensure this exists or it will just skip
    'include_headshot': True,
    'headshot_key': 'test/placeholder_headshot.png' 
}

# Create dummy placeholders if missing
storage = get_storage()
if not storage.exists('test/placeholder_logo.png'):
    storage.put_file(b'fake_png_data', 'test/placeholder_logo.png')
if not storage.exists('test/placeholder_headshot.png'):
    storage.put_file(b'fake_png_data', 'test/placeholder_headshot.png')

def run_verification():
    print("=== Starting SmartSign PDF Verification ===")
    
    layouts = ['smart_v1_minimal', 'smart_v1_agent_brand']
    sizes = ['12x18', '18x24', '24x36', '36x18', '36x24']
    
    failures = []
    
    # 1. New Layouts
    for layout in layouts:
        for size in sizes:
            print(f"\nTesting {layout} [{size}]...")
            asset = WORST_CASE_ASSET.copy()
            asset['layout_id'] = layout
            asset['print_size'] = size
            
            try:
                # Generate PDF
                pdf_key = generate_smartsign_pdf(asset, order_id=999)
                
                if not storage.exists(pdf_key):
                    failures.append(f"{layout} {size}: PDF Key {pdf_key} not found in storage.")
                    continue
                    
                pdf_data = storage.get_file(pdf_key).getvalue()
                pdf_size = len(pdf_data)
                print(f"  -> PDF Generated: {pdf_key} ({pdf_size} bytes)")
                if pdf_size < 1000:
                    failures.append(f"{layout} {size}: PDF too small ({pdf_size} bytes).")

                # Generate Preview
                # Note: preview generation might require poppler/imagemagick installed in env.
                # If this fails due to missing system dependencies, we'll note it but maybe not block if dev env is limited.
                try:
                    preview_key = render_pdf_to_web_preview(pdf_key, order_id=999, sign_size=size)
                    if not storage.exists(preview_key):
                         failures.append(f"{layout} {size}: Preview Key {preview_key} not found.")
                    else:
                         print(f"  -> Preview Generated: {preview_key}")
                except Exception as e:
                    failures.append(f"{layout} {size}: Preview Generation Crash: {e}")

            except Exception as e:
                failures.append(f"{layout} {size}: CRASH: {e}")
                import traceback
                traceback.print_exc()

    # 2. Regression: Legacy
    print("\nTesting Regression: smart_v1_photo_banner...")
    try:
        asset = WORST_CASE_ASSET.copy()
        asset['layout_id'] = 'smart_v1_photo_banner'
        asset['background_style'] = 'solid_blue'
        # Legacy doesn't use print_size usually, but new code wraps it. Default 18x24.
        
        pdf_key = generate_smartsign_pdf(asset, order_id=998)
        if storage.exists(pdf_key):
            print(f"  -> Legacy PDF Generated: {pdf_key}")
        else:
            failures.append("Legacy PDF not found")
            
    except Exception as e:
        failures.append(f"Legacy CRASH: {e}")

    print("\n=== Verification Summary ===")
    if failures:
        print("FAILURES FOUND:")
        for f in failures:
            print(f" - {f}")
        sys.exit(1)
    else:
        print("SUCCESS: All 11 combinations generated PDFs and Previews.")
        sys.exit(0)

if __name__ == "__main__":
    run_verification()
