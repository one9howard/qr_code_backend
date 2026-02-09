
import os
import sys
import shutil

# Setup path
sys.path.append(os.getcwd())

from services.pdf_smartsign import generate_smartsign_pdf
from utils.storage import get_storage
from config import INSTANCE_DIR, STATIC_DIR

def generate_preview():
    print("Generating Serif Preview with Headshot & Contact Info...")
    
    # 1. Setup Mock Headshot in Storage
    storage = get_storage()
    headshot_key = "uploads/mock/headshot.png"
    
    # Read a real image to use
    try:
        with open("static/img/current.png", "rb") as f:
            img_data = f.read()
        storage.put_file(img_data, headshot_key, content_type="image/png")
        print(f"Uploaded mock headshot to {headshot_key}")
    except Exception as e:
        print(f"Warning: Could not upload mock headshot: {e}")
        headshot_key = None

    # 2. Mock Asset
    asset = {
        'id': 'preview_asset',
        'code': 'SERIF-TEST',
        'agent_name': 'Jennifer Lawrence',
        'phone': '555.019.9999',  # Test dot format
        'email': 'jennifer@luxury-estates.com',
        'brokerage': 'Luxury Real Estate',
        'status_text': 'OPEN HOUSE',
        'cta_key': 'scan_for_details',
        'banner_color_id': 'navy',
        'layout_id': 'smart_v2_elegant_serif',
        'print_size': '18x24',
        'headshot_key': headshot_key,
        'agent_headshot_key': headshot_key # Fallback check
    }

    # 3. Generate
    # This saves to storage (instance/pdfs/...)
    key = generate_smartsign_pdf(asset, order_id='PREVIEW_SERIF', override_base_url='http://localhost:8080')
    print(f"Generated PDF key: {key}")

    # 4. Copy to Static for Viewing
    # LocalStorage saves to INSTANCE_DIR joined with key
    src_path = os.path.join(INSTANCE_DIR, key)
    dest_path = os.path.join(STATIC_DIR, "preview_serif.pdf")
    
    print(f"Copying from {src_path} to {dest_path}")
    
    if os.path.exists(src_path):
        shutil.copy2(src_path, dest_path)
        print(f"SUCCESS: Preview available at /static/preview_serif.pdf")
    else:
        print(f"ERROR: Source file not found at {src_path}")

if __name__ == "__main__":
    generate_preview()
