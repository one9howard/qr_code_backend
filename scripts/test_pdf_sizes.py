#!/usr/bin/env python
"""
Dev utility: Generate test PDFs for all sign sizes.
Run from project root: python scripts/test_pdf_sizes.py
"""
import os
import sys

# Path hack for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from utils.pdf_generator import generate_pdf_sign
from constants import SIGN_SIZES

def main():
    print("=" * 60)
    print("PDF SIZE TEST - Generating PDFs for all sign sizes")
    print("=" * 60)
    
    test_data = {
        "address": "123 Test Street",
        "beds": "4",
        "baths": "3",
        "sqft": "2500",
        "price": "$549,000",
        "agent_name": "Test Agent",
        "brokerage": "Test Realty",
        "agent_email": "test@example.com",
        "agent_phone": "(555) 123-4567",
        "qr_path": "",  # Skip QR for quick test
    }
    
    results = []
    for size in SIGN_SIZES.keys():
        print(f"\nGenerating {size}...")
        try:
            path = generate_pdf_sign(
                **test_data,
                sign_color="#1F6FEB",
                sign_size=size
            )
            file_size = os.path.getsize(path)
            results.append((size, "✅ OK", path, file_size))
            print(f"  Created: {path} ({file_size / 1024:.1f} KB)")
        except Exception as e:
            results.append((size, "❌ FAILED", str(e), 0))
            print(f"  Error: {e}")
    
    print("\n" + "=" * 60)
    print("RESULTS:")
    for size, status, path, file_size in results:
        if "OK" in status:
            print(f"  {size}: {status} → {os.path.basename(path)}")
        else:
            print(f"  {size}: {status} → {path}")
    print("=" * 60)
    print("\nOpen the PDFs to visually verify layout scales correctly.")

if __name__ == "__main__":
    main()
