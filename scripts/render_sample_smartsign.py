
import os
import sys
import shutil

# Add project root to path
sys.path.append(os.getcwd())

# ENV BYPASS for Config (Must be before imports)
os.environ.setdefault("DATABASE_URL", "postgresql://mock:5432/mock")
os.environ.setdefault("SECRET_KEY", "mock-secret")
os.environ.setdefault("PRINT_JOBS_TOKEN", "mock-token")
os.environ.setdefault("FLASK_ENV", "development")

from services.pdf_smartsign import generate_smartsign_pdf
from utils.pdf_preview import render_pdf_to_web_preview
from utils.storage import get_storage

def run():
    print("Generating Sample SmartSign (Photo Video Layout)...")
    
    # User's uploaded media path (from previous context metadata)
    # C:/Users/player1/.gemini/antigravity/brain/05b6190c-db87-48c8-a169-739d3cf53879/uploaded_media_0_1769625472150.png
    headshot_src = r"C:/Users/player1/.gemini/antigravity/brain/05b6190c-db87-48c8-a169-739d3cf53879/uploaded_media_0_1769625472150.png"
    
    storage = get_storage()
    
    # Store the headshot in our mock storage location
    headshot_key = "uploads/demo_headshot.png"
    if os.path.exists(headshot_src):
        with open(headshot_src, "rb") as f:
            storage.put_file(f, headshot_key)
    else:
        print(f"Warning: Source image not found at {headshot_src}. Using fallback monogram.")
        headshot_key = None

    # Mock Asset Data (Photo Banner Layout)
    asset = {
        'print_size': '18x24',
        'layout_id': 'smart_v1_photo_banner',
        'code': 'SAMPLE01',
        'brand_name': 'TEST1 AGENT',
        'phone': '(555) 555-5555',
        'email': 'test1@email.com',
        'brokerage_name': 'BROKERAGE NAME',
        'banner_color_id': 'blue', # Matches the user's "good" listing sign (blue)
        'cta_key': 'scan_for_details',
        'include_headshot': True,
        'headshot_key': headshot_key
    }
    
    # 1. Generate PDF
    pdf_key = generate_smartsign_pdf(asset, order_id=99999)
    print(f"PDF Generated key: {pdf_key}")
    
    # 2. Render Preview (WebP)
    # render_pdf_to_web_preview saves to storage key
    preview_key = render_pdf_to_web_preview(pdf_key, order_id=99999, sign_size='18x24')
    print(f"Preview Generated key: {preview_key}")
    
    # 3. Retrieve and Save Locally for User
    preview_data = storage.get_file(preview_key).getvalue()
    
    local_path = os.path.join(os.getcwd(), "sample_smartsign_preview.webp")
    with open(local_path, "wb") as f:
        f.write(preview_data)
        
    print(f"SAVED LOCAL PREVIEW: {local_path}")

if __name__ == "__main__":
    run()
