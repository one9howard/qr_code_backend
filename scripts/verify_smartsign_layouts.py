
import sys
import os
import fitz  # PyMuPDF
import io
from collections import namedtuple

# Add project root to path
sys.path.append(os.getcwd())

# ENV BYPASS for Config (Must be before imports)
os.environ.setdefault("DATABASE_URL", "postgresql://mock:5432/mock")
os.environ.setdefault("SECRET_KEY", "mock-secret")
os.environ.setdefault("PRINT_JOBS_TOKEN", "mock-token")
os.environ.setdefault("FLASK_ENV", "development")

from services.pdf_smartsign import generate_smartsign_pdf, SPECS, SmartSignLayout
from services.specs import SMARTSIGN_SIZES

from utils.storage import get_storage
from utils.pdf_preview import render_pdf_to_web_preview
from reportlab.lib.units import inch

# Mock Data
WORST_CASE_ASSET = {
    'code': 'ABCD1234',
    'brand_name': 'Alexandria Example',
    'phone': '(555) 555-5555',
    'email': 'alex@example.com',
    'brokerage_name': 'Example Realty – Peninsula Office',
    'banner_color_id': 'navy',
    'cta_key': 'scan_for_details',
    'include_logo': False,
    'include_headshot': False
}

LAYOUTS = ['smart_v1_minimal', 'smart_v1_agent_brand', 'smart_v1_photo_banner']
# Option A: Strict Sizes
SIZES = SMARTSIGN_SIZES

# Canonical Dimensions (Inches)
SIGN_SIZES = {
    '18x24': {'width_in': 18, 'height_in': 24},
    '24x36': {'width_in': 24, 'height_in': 36},
    '36x24': {'width_in': 36, 'height_in': 24},
}

def get_safe_rect(size_key):
    """Calculate safe rect in PDF points (0,0 at bottom-left of TRIM)."""
    size = SIGN_SIZES[size_key]
    w_pt = size['width_in'] * 72
    h_pt = size['height_in'] * 72
    
    spec_safe_margin = SPECS.get(size_key, SPECS['18x24'])['safe_margin']
    
    return {
        'x0': spec_safe_margin,
        'y0': spec_safe_margin,
        'x1': w_pt - spec_safe_margin,
        'y1': h_pt - spec_safe_margin,
        'w': w_pt,
        'h': h_pt,
        'margin': spec_safe_margin
    }

def verify_pdf_content(pdf_bytes, size_key, layout_id):
    """
    Open PDF with PyMuPDF.
    Verify:
    1. All text blocks are within Safe Rect.
    2. URL contains '/r/'.
    3. No overlapping text blocks.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc[0]
    
    # Coordinates Setup
    bleed = 0.125 * 72
    safe = get_safe_rect(size_key)
    page_h = page.rect.height
    
    # Safe Rect in PyMuPDF (Top-Left origin)
    # y1 (high val) in draw coords = near top = small y in PyMuPDF
    # y = page_height - (bleed + y_draw)
    # safe_y_top = page_h - (bleed + safe['y1'])
    # safe_y_bot = page_h - (bleed + safe['y0'])
    
    safe_box = fitz.Rect(
        bleed + safe['x0'],
        page_h - (bleed + safe['y1']),
        bleed + safe['x1'],
        page_h - (bleed + safe['y0'])
    )
    
    # Tolerance
    tolerance = 1.0
    safe_expanded = fitz.Rect(
        safe_box.x0 - tolerance,
        safe_box.y0 - tolerance,
        safe_box.x1 + tolerance,
        safe_box.y1 + tolerance
    )
    
    errors = []
    
    # Get Text Blocks
    text_page = page.get_text("dict")
    blocks = []
    
    found_url_correct = False
    
    for block in text_page["blocks"]:
        if "lines" not in block: continue
        bbox = fitz.Rect(block["bbox"])
        blocks.append(block)
        
        # 1. Safe Zone Check
        if not safe_expanded.contains(bbox):
            # Check intersection amount
            out_left = safe_expanded.x0 - bbox.x0
            out_right = bbox.x1 - safe_expanded.x1
            out_top = safe_expanded.y0 - bbox.y0
            out_bottom = bbox.y1 - safe_expanded.y1
            
            if out_left > 0.5 or out_right > 0.5 or out_top > 0.5 or out_bottom > 0.5:
                 content = ""
                 for line in block["lines"]:
                     for span in line["spans"]: content += span["text"]
                 errors.append(f"Safe Zone Breach: '{content[:15]}...' (Out: T{out_top:.1f}, B{out_bottom:.1f}, L{out_left:.1f}, R{out_right:.1f})")

        # 2. URL Check
        for line in block["lines"]:
            for span in line["spans"]:
                txt = span["text"]
                if "insite" in txt.lower() or "/r/" in txt:
                    if "/r/" in txt:
                        found_url_correct = True
                    elif "insite" in txt.lower() and "/r/" not in txt:
                        errors.append(f"Bad URL format: {txt}")

    if not found_url_correct:
         errors.append("Missing '/r/' URL fallback.")

    # 3. Overlap Check
    # We compare every block against every other block
    for i in range(len(blocks)):
        b1 = blocks[i]
        r1 = fitz.Rect(b1["bbox"])
        for j in range(i + 1, len(blocks)):
            b2 = blocks[j]
            r2 = fitz.Rect(b2["bbox"])
            
            # Intersection
            intersect = r1 & r2 # intersection rect
            if not intersect.is_empty:
                # Use tolerance. Sometimes bounding boxes touch or have tiny overlap
                if intersect.width > 1.0 and intersect.height > 1.0:
                    # Check for phantom horizontal overlap (PyMuPDF merge artifact)
                    # If one block is nearly full width, it overlaps everything on the line. Ignore.
                    # Get content for error msg
                    c1 = " ".join([s["text"] for l in b1["lines"] for s in l["spans"]])
                    c2 = " ".join([s["text"] for l in b2["lines"] for s in l["spans"]])

                    # Check for phantom horizontal overlap (PyMuPDF merge artifact)
                    # If one block is nearly full width, it overlaps everything on the line. Ignore.
                    page_width = page.rect.width
                    if (r1.width > page_width * 0.85) or (r2.width > page_width * 0.85):
                        print(f"  [WARN] Ignoring phantom overlap: '{c1[:10]}' vs '{c2[:10]}' (width > 85%)")
                        continue

                    # Get content for error msg
                    c1 = " ".join([s["text"] for l in b1["lines"] for s in l["spans"]])
                    c2 = " ".join([s["text"] for l in b2["lines"] for s in l["spans"]])
                    errors.append(f"Overlap Detected: ['{c1[:10]}'] {r1} vs ['{c2[:10]}'] {r2}")

    return errors

def run():
    print("=== SmartSign Layout Verification (Legacy Optimized) ===")
    storage = get_storage()
    
    # OUTPUT FILE
    out_f = open("verify_output.txt", "w", encoding="utf-8")
    
    total_tests = len(SIZES) * len(LAYOUTS)
    passed = 0
    
    for size in SIZES:
        for layout in LAYOUTS:
            msg = f"Testing {size} / {layout} ... "
            print(msg, end="")
            out_f.write(msg)
            
            asset = WORST_CASE_ASSET.copy()
            asset['print_size'] = size
            asset['layout_id'] = layout
            
            try:
                # 1. Generate PDF (Force New by Random ID)
                import random
                oid = random.randint(10000, 99999)
                pdf_key = generate_smartsign_pdf(asset, order_id=oid)
                pdf_bytes = storage.get_file(pdf_key).getvalue()
                
                # 2. Verify Content
                errors = verify_pdf_content(pdf_bytes, size, layout)
                
                # 3. Verify Preview Generation (Crash Check)
                try:
                    render_pdf_to_web_preview(pdf_key, order_id=9999, sign_size=size)
                except Exception as e:
                    errors.append(f"Preview Generation Failed: {e}")
                
                if not errors:
                    print("PASS")
                    out_f.write("PASS\n")
                    passed += 1
                else:
                    print("FAIL")
                    out_f.write("FAIL\n")
                    for e in errors:
                        print(f"  - {e}")
                        out_f.write(f"  - {e}\n")
                        
            except Exception as e:
                print(f"CRASH: {e}")
                out_f.write(f"CRASH: {e}\n")
                import traceback
                traceback.print_exc()

    print(f"\nSummary: {passed}/{total_tests} passed.")
    if passed < total_tests:
        sys.exit(1)
    else:
        sys.exit(0)

if __name__ == "__main__":
    run()
