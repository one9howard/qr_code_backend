"""
Generate sample PDFs for all supported sizes.
Used to visually verify font sizing and layout after changes.

Usage:
    python scripts/generate_sample_pdfs.py
"""
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.pdf_generator import generate_pdf_sign
from constants import SIGN_SIZES
from config import BASE_DIR

# Sample data
SAMPLE_ADDRESS = "123 Maple Street"
SAMPLE_BEDS = "4"
SAMPLE_BATHS = "3"
SAMPLE_SQFT = "2,450"
SAMPLE_PRICE = "$549,900"
SAMPLE_AGENT_NAME = "Jane Doe"
SAMPLE_BROKERAGE = "Premier Real Estate"
SAMPLE_AGENT_EMAIL = "jane@premierrealty.com"
SAMPLE_AGENT_PHONE = "(555) 123-4567"

# Output directory
OUTPUT_DIR = os.path.join(BASE_DIR, "sample_pdfs")


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # Need a sample QR code - use existing or create placeholder
    qr_path = os.path.join(BASE_DIR, "static", "qr", "sample.png")
    
    # Check if we have a sample QR, if not create a simple one
    if not os.path.exists(qr_path):
        print("Note: No sample QR code found. Using placeholder path.")
        qr_path = None
    
    print(f"Generating sample PDFs in: {OUTPUT_DIR}\n")
    
    for size_key in SIGN_SIZES.keys():
        print(f"Generating {size_key}...", end=" ")
        
        try:
            # Generate to temp path (no order_id)
            pdf_path = generate_pdf_sign(
                address=SAMPLE_ADDRESS,
                beds=SAMPLE_BEDS,
                baths=SAMPLE_BATHS,
                sqft=SAMPLE_SQFT,
                price=SAMPLE_PRICE,
                agent_name=SAMPLE_AGENT_NAME,
                brokerage=SAMPLE_BROKERAGE,
                agent_email=SAMPLE_AGENT_EMAIL,
                agent_phone=SAMPLE_AGENT_PHONE,
                qr_path=qr_path,
                agent_photo_path=None,
                sign_color="#1F6FEB",
                sign_size=size_key,
                order_id=None,  # Will use temp path
            )
            
            # Copy to sample output directory with clear name
            output_filename = f"sample_{size_key}.pdf"
            output_path = os.path.join(OUTPUT_DIR, output_filename)
            
            # Move from temp location
            import shutil
            shutil.move(pdf_path, output_path)
            
            print(f"✓ {output_filename}")
            
        except Exception as e:
            print(f"✗ Error: {e}")
    
    print(f"\n✅ Sample PDFs saved to: {OUTPUT_DIR}")
    print("Open these files to visually verify font sizing and layout.")


if __name__ == "__main__":
    main()
