import sys
import os
import fitz  # PyMuPDF
import io
from collections import namedtuple

# Add project root to path
sys.path.append(os.getcwd())

from services.pdf_smartsign import generate_smartsign_pdf, SPECS, SIGN_SIZES, SmartSignLayout
from utils.storage import get_storage
from reportlab.lib.units import inch

# Mock Data
WORST_CASE_ASSET = {
    'code': 'ABCD1234',
    'brand_name': 'Alexandria Catherine Van Der Westhuizen',
    'phone': '(555) 555-5555',
    'email': 'alexandria.vanderwesthuizen.longemailaddress@gmail.com',
    'brokerage_name': 'Sotheby’s International Realty – Northern California Peninsula',
    'banner_color_id': 'navy',
    'cta_key': 'scan_for_details',
    'include_logo': False,  # Test text fallback mostly
    'include_headshot': False
}

LAYOUTS = ['smart_v1_minimal', 'smart_v1_agent_brand']
SIZES = ['12x18', '18x24', '24x36', '36x18', '36x24']

def get_safe_rect(size_key):
    """Calculate safe rect in PDF points (0,0 at bottom-left of TRIM)."""
    # PDF Generator is (width+bleed, height+bleed).
    # Origin is translated to (bleed, bleed).
    # So drawing coordinates are (0..width, 0..height).
    # Safe Rect is trim inset by safe_margin.
    
    size = SIGN_SIZES[size_key]
    w_pt = size['width_in'] * 72
    h_pt = size['height_in'] * 72
    
    # Get safe margin from SPECS
    # We need to instantiate SmartSignLayout to get the resolved logic or access SPECS directly
    # SPECS structure: SPECS[size_key] might need fallback logic if key missing (handled in Layout class)
    # But SPECS keys match SIZES list.
    
    spec_safe_margin = SPECS.get(size_key, SPECS['18x24'])['safe_margin']
    
    # Safe Rect in Drawing Coordinates:
    # x: safe_margin to width - safe_margin
    # y: safe_margin to height - safe_margin
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
    1. All text blocks are within Safe Rect (account for Bleed offset).
    2. URL contains '/r/'.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc[0]
    
    # PDF Page Size includes BLEED.
    # PyMuPDF coords are from bottom-left (if using certain methods) or top-left.
    # rect is (x0, y0, x1, y1). fitz uses top-left origin by default? 
    # Actually fitz.Rect is usually (x0, y0, x1, y1). To coordinate with ReportLab's bottom-up,
    # we need to check page.rect.
    
    # ReportLab default: Bottom-Left origin.
    # PyMuPDF: Top-Left origin usually for rendering, but text extraction returns Rect objects.
    # We need to normalize.
    # Let's use `page.get_text("dict")` which returns blocks with bbox.
    # Coords are usually PDF standard (Bottom-Left) if not specified? 
    # NO: PyMuPDF docs say "Coordinates are usually in points... Origin is top-left of the page."
    # WAIT. PDF native is Bottom-Left. ReportLab writes Bottom-Left.
    # PyMuPDF reads PDF. `page.rect` is usually (0, 0, width, height).
    
    # Let's map Safe Rect to PyMuPDF coordinates.
    # Page Width = w_pt + 2*bleed
    # Page Height = h_pt + 2*bleed
    bleed = 0.125 * 72
    
    safe = get_safe_rect(size_key)
    
    # Transform Drawing Coords (0,0 = Trim Bottom-Left) to Page Coords (0,0 = Page Top-Left)
    # Drawing (x,y) -> Page (bleed + x, page_height - (bleed + y)) ??
    # PyMuPDF: y grows DOWN.
    # PDF/ReportLab: y grows UP.
    
    # Drawing Geometry:
    # Bottom Left of Trim is at (bleed, bleed) in PDF User Space (if origin was 0,0).
    # But generator does `c.translate(bleed, bleed)`. So drawing (0,0) ends up at user space (bleed, bleed).
    
    # Verify mapping:
    # Drawing Point (x,y) -> PDF User Space (x+bleed, y+bleed).
    # PyMuPDF extracts coords in PDF User Space (usually relative to bottom-left for text? or top-left?)
    # "The coordinate system ... has its origin (0,0) in the top-left corner of the page." (PyMuPDF docs).
    # So `y` is distance from top.
    
    page_h = page.rect.height
    
    # Safe Rect in PyMuPDF (Top-Left origin):
    # Left: bleed + safe.x0
    # Right: bleed + safe.x1
    # Top: page_h - (bleed + safe.y1)  (since y1 is near top in drawing coords)
    # Bottom: page_h - (bleed + safe.y0)
    
    # Wait, safe.y1 is TOP of safe zone in drawing coords (high value).
    # So distance from page top = page_h - (bleed + safe.y1).
    
    safe_box = fitz.Rect(
        bleed + safe['x0'],
        page_h - (bleed + safe['y1']),
        bleed + safe['x1'],
        page_h - (bleed + safe['y0'])
    )
    
    # Allow 1pt tolerance
    tolerance = 1.0
    safe_expanded = fitz.Rect(
        safe_box.x0 - tolerance,
        safe_box.y0 - tolerance,
        safe_box.x1 + tolerance,
        safe_box.y1 + tolerance
    )
    
    errors = []
    
    # 1. Text Check
    text_page = page.get_text("dict")
    found_url_correct = False
    
    for block in text_page["blocks"]:
        if "lines" not in block: continue
        bbox = fitz.Rect(block["bbox"])
        
        # Check containment
        if not safe_expanded.contains(bbox):
            # Partial overlap allowed? No. "All text must be inside safe rect"
            # BUT: PyMuPDF bbox might be slightly larger than visual ink.
            # Let's check intersection. If fully contained, good.
            # If slightly out, check how much.
            
            # Helper to check outliers
            out_left = safe_expanded.x0 - bbox.x0
            out_right = bbox.x1 - safe_expanded.x1
            out_top = safe_expanded.y0 - bbox.y0 # bbox.y0 is top
            out_bottom = bbox.y1 - safe_expanded.y1
            
            # Ignore if outlier is negligible (< 1pt) - already handled by expanded
            if out_left > 0 or out_right > 0 or out_top > 0 or out_bottom > 0:
                 # It's an error.
                 # Get text content
                 content = ""
                 for line in block["lines"]:
                     for span in line["spans"]:
                         content += span["text"]
                 
                 errors.append(f"Text outside safe zone: '{content[:20]}...' Exceeded by L:{out_left:.2f} R:{out_right:.2f} T:{out_top:.2f} B:{out_bottom:.2f}")

        # Check URL
        for line in block["lines"]:
            for span in line["spans"]:
                txt = span["text"]
                if "insite" in txt.lower() or "/r/" in txt:
                    if "/r/" in txt:
                        found_url_correct = True
                    elif "insite" in txt.lower() and "/r/" not in txt:
                        errors.append(f"Printed URL missing '/r/': {txt}")

    if not found_url_correct:
        errors.append("Could not find a text block with '/r/' in it.")

    return errors

def run():
    print("=== SmartSign Spec Verification ===")
    storage = get_storage()
    
    # Ensure updated pdf logic is imported (fresh)
    # (Since we are running this script as a generic main, it will import current files)
    
    for size in SIZES:
        for layout in LAYOUTS:
            print(f"Testing {size} / {layout} ... ", end="")
            
            asset = WORST_CASE_ASSET.copy()
            asset['print_size'] = size
            asset['layout_id'] = layout
            
            # Generate
            try:
                # We need to bypass the 'row' vs 'dict' check in generate helper if it exists?
                # generate_smartsign_pdf accepts dict.
                pdf_key = generate_smartsign_pdf(asset, order_id=9999)
                pdf_bytes = storage.get_file(pdf_key).getvalue()
                
                # Check
                errors = verify_pdf_content(pdf_bytes, size, layout)
                
                if not errors:
                    print("PASS")
                else:
                    print("FAIL")
                    for e in errors:
                        print(f"  - {e}")
                    sys.exit(1)
                    
            except Exception as e:
                print(f"CRASH: {e}")
                import traceback
                traceback.print_exc()
                sys.exit(1)

    print("\nSUCCESS: All 10 combinations passed Safe Zone and Content checks.")

if __name__ == "__main__":
    run()
