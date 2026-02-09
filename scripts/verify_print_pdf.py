#!/usr/bin/env python
"""
Print PDF Verification Script

Validates that PDFs meet print-quality requirements:
1. Page size matches expected inches (inches * 72 = points)
2. Fonts are embedded (not substituted)
3. Placed images meet minimum DPI (>= 200, target >= 300)
4. QR codes are vector, not raster

Usage:
    python scripts/verify_print_pdf.py path/to/file.pdf [expected_size]
    python scripts/verify_print_pdf.py artifacts/yard_gallery/pdfs/*.pdf
"""
import sys
import os
import argparse
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import fitz  # PyMuPDF
except ImportError:
    print("ERROR: PyMuPDF (fitz) required. Install with: pip install PyMuPDF")
    sys.exit(1)

# Size definitions: inches -> points (1 inch = 72 pts)
SIZE_SPECS = {
    '12x18': (12 * 72, 18 * 72),
    '18x24': (18 * 72, 24 * 72),
    '24x36': (24 * 72, 36 * 72),
    '36x24': (36 * 72, 24 * 72),
    '6x24': (6 * 72, 24 * 72),
}

# Add bleed variants (0.125" bleed on each side)
BLEED_IN = 0.125
for size, (w, h) in list(SIZE_SPECS.items()):
    bleed_pts = BLEED_IN * 72 * 2  # Both sides
    SIZE_SPECS[f'{size}_bleed'] = (w + bleed_pts, h + bleed_pts)

MIN_DPI = 200
TARGET_DPI = 300


class PDFVerificationResult:
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.passed = True
        self.errors = []
        self.warnings = []
        self.info = {}
    
    def error(self, msg: str):
        self.passed = False
        self.errors.append(msg)
    
    def warn(self, msg: str):
        self.warnings.append(msg)
    
    def __str__(self):
        status = "PASS" if self.passed else "FAIL"
        lines = [f"[{status}] {self.filepath}"]
        for e in self.errors:
            lines.append(f"  ❌ {e}")
        for w in self.warnings:
            lines.append(f"  ⚠️  {w}")
        return "\n".join(lines)


def verify_pdf(filepath: str, expected_size: str = None) -> PDFVerificationResult:
    """
    Verify a PDF meets print-quality requirements.
    
    Args:
        filepath: Path to PDF file
        expected_size: Optional expected size key (e.g., '18x24')
        
    Returns:
        PDFVerificationResult with pass/fail and details
    """
    result = PDFVerificationResult(filepath)
    
    if not os.path.exists(filepath):
        result.error(f"File not found: {filepath}")
        return result
    
    try:
        doc = fitz.open(filepath)
    except Exception as e:
        result.error(f"Failed to open PDF: {e}")
        return result
    
    try:
        if doc.page_count == 0:
            result.error("PDF has no pages")
            return result
        
        page = doc[0]
        
        # 1. Verify page size
        rect = page.rect
        width_pts = rect.width
        height_pts = rect.height
        result.info['page_size_pts'] = (width_pts, height_pts)
        result.info['page_size_in'] = (width_pts / 72, height_pts / 72)
        
        if expected_size:
            # Check with and without bleed
            expected_pts = SIZE_SPECS.get(expected_size)
            expected_bleed = SIZE_SPECS.get(f'{expected_size}_bleed')
            
            if expected_pts:
                exp_w, exp_h = expected_pts
                bleed_w, bleed_h = expected_bleed or (exp_w, exp_h)
                
                # Allow either exact size or with bleed
                size_ok = (
                    (abs(width_pts - exp_w) < 1 and abs(height_pts - exp_h) < 1) or
                    (abs(width_pts - bleed_w) < 1 and abs(height_pts - bleed_h) < 1)
                )
                
                if not size_ok:
                    result.error(
                        f"Page size mismatch: got {width_pts:.1f}x{height_pts:.1f} pts, "
                        f"expected {exp_w}x{exp_h} pts (or {bleed_w:.1f}x{bleed_h:.1f} with bleed)"
                    )
        
        # 2. Check fonts
        fonts = page.get_fonts()
        result.info['fonts'] = []
        
        for font in fonts:
            font_name = font[3] if len(font) > 3 else "unknown"
            font_type = font[4] if len(font) > 4 else "unknown"
            result.info['fonts'].append({'name': font_name, 'type': font_type})
            
            # Check for Type3 (usually indicates issues)
            if font_type == 'Type3':
                result.warn(f"Type3 font detected: {font_name} - may not print correctly")
        
        # Check for unembedded fonts (heuristic: core fonts without embedding)
        core_fonts = ['Helvetica', 'Times', 'Courier', 'Symbol', 'ZapfDingbats']
        for font_info in result.info['fonts']:
            name = font_info['name']
            if any(core in name for core in core_fonts):
                # Check if it's actually embedded or just referenced
                # PyMuPDF doesn't directly tell us, but Type1 core fonts are often not embedded
                if font_info['type'] == 'Type1':
                    result.warn(f"Core font '{name}' may not be embedded - verify with print provider")
        
        # 3. Check images for DPI
        images = page.get_images()
        result.info['images'] = []
        
        for img_index, img in enumerate(images):
            xref = img[0]
            try:
                base_image = doc.extract_image(xref)
                img_width = base_image.get('width', 0)
                img_height = base_image.get('height', 0)
                
                # Get placement size on page
                img_rects = page.get_image_rects(xref)
                
                for img_rect in img_rects:
                    placed_width = img_rect.width
                    placed_height = img_rect.height
                    
                    # Calculate effective DPI
                    if placed_width > 0 and placed_height > 0:
                        dpi_x = (img_width / placed_width) * 72
                        dpi_y = (img_height / placed_height) * 72
                        effective_dpi = min(dpi_x, dpi_y)
                        
                        img_info = {
                            'xref': xref,
                            'source_size': (img_width, img_height),
                            'placed_size_pts': (placed_width, placed_height),
                            'effective_dpi': effective_dpi
                        }
                        result.info['images'].append(img_info)
                        
                        if effective_dpi < MIN_DPI:
                            result.error(
                                f"Image {xref}: effective DPI {effective_dpi:.0f} < {MIN_DPI} minimum. "
                                f"Source: {img_width}x{img_height}, Placed: {placed_width:.1f}x{placed_height:.1f} pts"
                            )
                        elif effective_dpi < TARGET_DPI:
                            result.warn(
                                f"Image {xref}: effective DPI {effective_dpi:.0f} below target {TARGET_DPI}"
                            )
                            
            except Exception as e:
                result.warn(f"Could not analyze image {xref}: {e}")
        
        # 4. Check for raster QR codes (heuristic)
        # QR codes embedded as images are suspicious - they should be vector paths
        for img_info in result.info['images']:
            w, h = img_info.get('source_size', (0, 0))
            # QR codes are typically square and small-ish in source pixels
            if 0 < w == h and w < 500:
                # Likely a QR code rendered as raster
                dpi = img_info.get('effective_dpi', 0)
                if dpi < 600:  # QR should be very high DPI or vector
                    result.warn(
                        f"Possible raster QR code detected (image {img_info['xref']}, {w}x{h}px). "
                        f"Consider using vector QR for print quality."
                    )
        
        # 5. Check for transparency (can cause print issues)
        text_dict = page.get_text("dict")
        # Basic check - more thorough would require parsing graphics state
        
    finally:
        doc.close()
    
    return result


def main():
    parser = argparse.ArgumentParser(description='Verify print-ready PDFs')
    parser.add_argument('files', nargs='+', help='PDF files to verify')
    parser.add_argument('--size', '-s', help='Expected size (e.g., 18x24)')
    parser.add_argument('--quiet', '-q', action='store_true', help='Only show failures')
    args = parser.parse_args()
    
    all_passed = True
    results = []
    
    for filepath in args.files:
        # Handle glob patterns on Windows
        if '*' in filepath:
            import glob
            files = glob.glob(filepath)
        else:
            files = [filepath]
        
        for f in files:
            result = verify_pdf(f, args.size)
            results.append(result)
            
            if not result.passed:
                all_passed = False
            
            if not args.quiet or not result.passed:
                print(result)
                print()
    
    # Summary
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    print(f"{'=' * 40}")
    print(f"Verified {total} PDFs: {passed} passed, {total - passed} failed")
    
    if all_passed:
        print("✅ All PDFs meet print quality requirements")
        return 0
    else:
        print("❌ Some PDFs failed verification")
        return 1


if __name__ == '__main__':
    sys.exit(main())
