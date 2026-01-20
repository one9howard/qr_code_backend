import os
import sys

# Add parent directory to path to allow imports from app root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.pdf_generator import generate_pdf_sign
from utils.pdf_preview import render_pdf_to_web_preview
from utils.qr_generator import generate_qr
from config import BASE_URL

def verify_layouts():
    print("Starting layout verification...")
    
    # Test Data
    test_data = {
        "address": "123 Test Blvd",
        "beds": "4",
        "baths": "3.5",
        "sqft": "2500",
        "price": "1,250,000",
        "agent_name": "Jane Doe",
        "brokerage": "Premier Realty",
        "agent_email": "jane@example.com",
        "agent_phone": "555-0199",
        "sign_color": "#1F6FEB"
    }

    # Assets
    # Assuming run from root or sensitive to CWD
    # We will run this from root: python -m scripts.verify_layouts or python scripts/verify_layouts.py
    # Use absolute paths for assets to be safe
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    agent_photo_path = os.path.join(base_dir, "sample_photos", "1headshot.webp")
    
    # Generate a dummy QR
    print("Generating dummy QR...")
    qr_filename = generate_qr("https://example.com/p/test-property", "test-property-qr")
    # qr_filename is absolute path from generate_qr or relative?
    # utils.qr_generator usually returns full path or relative to static?
    # Let's check imports. usually it saves to static/qr
    
    # Check if qr_filename is absolute, if not make it so
    if not os.path.isabs(qr_filename):
         # It likely returns path relative to where it was run or just filename
         # The generate_qr function in this codebase (from memory) uses QR_PATH from config
         pass

    # Normalize paths for PDF generator
    # pdf_generator expects absolute paths or paths relative to CWD
    
    sizes_to_test = ["18x24", "24x36", "36x18"]
    
    for size in sizes_to_test:
        print(f"\nTesting size: {size}")
        try:
            pdf_path = generate_pdf_sign(
                address=test_data["address"],
                beds=test_data["beds"],
                baths=test_data["baths"],
                sqft=test_data["sqft"],
                price=test_data["price"],
                agent_name=test_data["agent_name"],
                brokerage=test_data["brokerage"],
                agent_email=test_data["agent_email"],
                agent_phone=test_data["agent_phone"],
                qr_path=qr_filename,
                agent_photo_path=agent_photo_path,
                sign_color=test_data["sign_color"],
                sign_size=size
            )
            print(f"  [OK] PDF generated: {pdf_path}")
            
            # Generate WebP Preview (modern format, replaces deprecated PNG)
            webp_path = render_pdf_to_web_preview(pdf_path, sign_size=size)
            print(f"  [OK] Preview generated: {webp_path}")
            
        except Exception as e:
            print(f"  [FAIL] Error processing {size}: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    verify_layouts()
