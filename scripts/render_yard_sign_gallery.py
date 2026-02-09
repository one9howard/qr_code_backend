#!/usr/bin/env python
"""
Yard Sign Render Gallery Generator

Generates a deterministic set of yard sign PDFs and WEBP previews for visual QA.
No database, Stripe, or external services required.

Output:
    artifacts/yard_gallery/pdfs/           - PDF files
    artifacts/yard_gallery/previews/       - WEBP previews
    artifacts/yard_gallery/index.html      - Visual gallery
    
Usage:
    python scripts/render_yard_sign_gallery.py
"""
import sys
import os
import io
import json
from pathlib import Path
from datetime import datetime

# Allow running without DB config
os.environ["ALLOW_MISSING_DB"] = "1"

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import after path setup
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import inch
from PIL import Image
import fitz  # PyMuPDF

# Local imports
from services.printing.layout_utils import register_fonts
from constants import SIGN_SIZES

# Output directories
GALLERY_DIR = PROJECT_ROOT / 'artifacts' / 'yard_gallery'
PDF_DIR = GALLERY_DIR / 'pdfs'
PREVIEW_DIR = GALLERY_DIR / 'previews'

# Yard sign layouts to render
YARD_LAYOUTS = [
    'yard_modern_round',
    'yard_phone_qr_premium',
    'yard_address_qr_premium',
]

# Sizes to render for each layout
YARD_SIZES = ['18x24', '24x36', '36x24']

# Test samples - worst-case scenarios for text fitting
SAMPLES = [
    {
        'name': 'typical',
        'address': '123 Main Street',
        'city': 'Springfield',
        'state': 'IL',
        'zip': '62701',
        'price': '$425,000',
        'beds': 4,
        'baths': 2.5,
        'sqft': 2150,
        'agent_name': 'Jane Smith',
        'brokerage': 'Elite Realty',
        'phone': '(555) 123-4567',
        'email': 'jane@eliterealty.com',
        'cta': 'SCAN FOR INFO',
    },
    {
        'name': 'long_address',
        'address': '12345 Northwest Brookhaven Boulevard Apartment 2507',
        'city': 'San Francisco',
        'state': 'CA',
        'zip': '94102',
        'price': '$1,875,000',
        'beds': 3,
        'baths': 2,
        'sqft': 1850,
        'agent_name': 'John Doe',
        'brokerage': 'Bay Area Properties',
        'phone': '(415) 555-1234',
        'email': 'john@bayprops.com',
        'cta': 'SCAN FOR DETAILS',
    },
    {
        'name': 'long_brokerage',
        'address': '789 Oak Lane',
        'city': 'Chicago',
        'state': 'IL',
        'zip': '60601',
        'price': '$650,000',
        'beds': 5,
        'baths': 3,
        'sqft': 3200,
        'agent_name': 'Sarah Johnson',
        'brokerage': 'Coldwell Banker International Real Estate Group Associates LLC',
        'phone': '(312) 555-9876',
        'email': 'sarah@cbintl.com',
        'cta': 'SCAN ME',
    },
    {
        'name': 'missing_sqft',
        'address': '456 Elm Street',
        'city': 'Austin',
        'state': 'TX',
        'zip': '78701',
        'price': '$550,000',
        'beds': 3,
        'baths': 2,
        'sqft': None,
        'agent_name': 'Mike Chen',
        'brokerage': 'Austin Homes',
        'phone': '(512) 555-4321',
        'email': 'mike@austinhomes.com',
        'cta': 'SCAN FOR INFO',
    },
    {
        'name': 'missing_phone',
        'address': '321 Pine Road',
        'city': 'Denver',
        'state': 'CO',
        'zip': '80202',
        'price': '$875,000',
        'beds': 4,
        'baths': 3.5,
        'sqft': 2800,
        'agent_name': 'Lisa Park',
        'brokerage': 'Mountain View Realty',
        'phone': None,
        'email': 'lisa@mtviewrealty.com',
        'cta': 'SCAN FOR DETAILS',
    },
    {
        'name': 'long_agent_name',
        'address': '555 Cedar Avenue',
        'city': 'Seattle',
        'state': 'WA',
        'zip': '98101',
        'price': '$1,250,000',
        'beds': 4,
        'baths': 3,
        'sqft': 2400,
        'agent_name': 'Christopher Alexander Montgomery-Worthington III',
        'brokerage': 'Pacific NW Properties',
        'phone': '(206) 555-7890',
        'email': 'cam@pacificnw.com',
        'cta': 'SCAN FOR INFO',
    },
    {
        'name': 'no_price',
        'address': '888 Luxury Lane',
        'city': 'Miami',
        'state': 'FL',
        'zip': '33101',
        'price': None,
        'beds': 6,
        'baths': 5,
        'sqft': 5500,
        'agent_name': 'Carlos Rodriguez',
        'brokerage': 'Luxury Living',
        'phone': '(305) 555-0000',
        'email': 'carlos@luxliving.com',
        'cta': 'CALL FOR PRICE',
    },
    {
        'name': 'condo_unit',
        'address': '100 Park Avenue #1207',
        'city': 'New York',
        'state': 'NY',
        'zip': '10017',
        'price': '$2,450,000',
        'beds': 2,
        'baths': 2,
        'sqft': 1400,
        'agent_name': 'Amanda Lee',
        'brokerage': 'Manhattan Estates',
        'phone': '(212) 555-1212',
        'email': 'amanda@manhattanest.com',
        'cta': 'SCAN FOR INFO',
    },
    {
        'name': 'rural_address',
        'address': 'Rural Route 7, Box 234-A',
        'city': 'Springfield',
        'state': 'MO',
        'zip': '65802',
        'price': '$185,000',
        'beds': 3,
        'baths': 1,
        'sqft': 1200,
        'agent_name': 'Bob Wilson',
        'brokerage': 'Country Properties LLC',
        'phone': '(417) 555-3456',
        'email': 'bob@countryprop.com',
        'cta': 'SCAN FOR DETAILS',
    },
]


def ensure_directories():
    """Create output directories if they don't exist."""
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)


def render_pdf_to_preview(pdf_bytes: bytes, output_path: Path, bleed_in: float = 0.125):
    """Render PDF to WEBP preview, cropping bleed."""
    doc = fitz.open(stream=pdf_bytes, filetype='pdf')
    
    try:
        page = doc[0]
        
        # Calculate DPI to get ~2000px max dimension
        rect = page.rect
        max_dim = max(rect.width, rect.height) / 72  # inches
        target_dpi = min(300, int(2000 / max_dim))
        
        zoom = target_dpi / 72
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        
        img = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
        
        # Crop bleed
        bleed_px = int(bleed_in * target_dpi)
        if bleed_px > 0:
            img = img.crop((bleed_px, bleed_px, img.width - bleed_px, img.height - bleed_px))
        
        img.save(output_path, 'WEBP', quality=85)
        
    finally:
        doc.close()


def render_yard_sign(layout_id: str, size: str, sample: dict) -> bytes:
    """
    Render a yard sign PDF for the given layout/size/sample.
    Returns PDF bytes.
    """
    # Get size config
    if size not in SIGN_SIZES:
        size = '18x24'
    
    size_config = SIGN_SIZES[size]
    width_in = size_config['width_in']
    height_in = size_config['height_in']
    bleed = 0.125
    
    width_pts = (width_in + 2 * bleed) * 72
    height_pts = (height_in + 2 * bleed) * 72
    
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(width_pts, height_pts))
    
    # Translate for bleed
    c.saveState()
    c.translate(bleed * 72, bleed * 72)
    
    # Import renderer based on layout
    if layout_id == 'yard_modern_round':
        from utils.pdf_generator import _draw_modern_round_layout, LayoutSpec
        layout = LayoutSpec(width_in, height_in)
        
        _draw_modern_round_layout(
            c, layout,
            address=sample['address'],
            beds=sample.get('beds'),
            baths=sample.get('baths'),
            sqft=sample.get('sqft'),
            price=sample.get('price', ''),
            agent_name=sample['agent_name'],
            brokerage=sample['brokerage'],
            agent_email=sample.get('email', ''),
            agent_phone=sample.get('phone', ''),
            qr_key=None,
            agent_photo_key=None,
            sign_color='#0f172a',
            qr_value=f"https://example.com/p/demo_{sample['name']}",
            user_id=None,
            logo_key=None
        )
        
    elif layout_id in ('yard_phone_qr_premium', 'yard_address_qr_premium'):

        from utils.listing_designs import _draw_yard_phone_qr_premium, _draw_yard_address_qr_premium
        from utils.pdf_generator import LayoutSpec
        layout = LayoutSpec(width_in, height_in)
        
        args = {
            'address': sample['address'],
            'beds': sample.get('beds'),
            'baths': sample.get('baths'),
            'sqft': sample.get('sqft'),
            'price': sample.get('price', ''),
            'agent_name': sample['agent_name'],
            'brokerage': sample['brokerage'],
            'agent_email': sample.get('email', ''),
            'agent_phone': sample.get('phone', ''),
            'qr_key': None,
            'agent_photo_key': None,
            'sign_color': '#0f172a',
            'qr_value': f"https://example.com/p/demo_{sample['name']}",
            'user_id': None,
            'logo_key': None,
            'license_number': 'DRE#12345678',
            'state': sample.get('state', 'CA'),
            'city': sample.get('city', ''),
        }
        
        if layout_id == 'yard_phone_qr_premium':
            _draw_yard_phone_qr_premium(c, layout, **args)
        else:
            _draw_yard_address_qr_premium(c, layout, **args)
    
    else:
        # Fallback: just draw a placeholder
        c.setFont('Helvetica', 24)
        c.drawCentredString(width_in * 36, height_in * 36, f"Layout: {layout_id}")
    
    c.restoreState()
    c.showPage()
    c.save()
    
    return buf.getvalue()


def generate_gallery():
    """Generate the complete yard sign gallery."""
    print("=" * 60)
    print("Yard Sign Render Gallery Generator")
    print("=" * 60)
    
    # Register fonts
    print("\n1. Registering fonts...")
    register_fonts()
    print("   ✓ Fonts registered")
    
    # Create directories
    print("\n2. Creating output directories...")
    ensure_directories()
    print(f"   ✓ PDF dir: {PDF_DIR}")
    print(f"   ✓ Preview dir: {PREVIEW_DIR}")
    
    # Generate PDFs and previews
    print("\n3. Generating signs...")
    
    results = []
    pdf_count = 0
    webp_count = 0
    errors = []
    
    for layout_id in YARD_LAYOUTS:
        for size in YARD_SIZES:
            for sample in SAMPLES:
                sample_name = sample['name']
                filename_base = f"{layout_id}_{size}_{sample_name}"
                
                pdf_path = PDF_DIR / f"{filename_base}.pdf"
                preview_path = PREVIEW_DIR / f"{filename_base}.webp"
                
                try:
                    # Render PDF
                    pdf_bytes = render_yard_sign(layout_id, size, sample)
                    
                    with open(pdf_path, 'wb') as f:
                        f.write(pdf_bytes)
                    pdf_count += 1
                    
                    # Render preview
                    render_pdf_to_preview(pdf_bytes, preview_path)
                    webp_count += 1
                    
                    # Verify PDF (optional - import if available)
                    verification = None
                    try:
                        from scripts.verify_print_pdf import verify_pdf
                        verification = verify_pdf(str(pdf_path), size)
                    except ImportError:
                        pass
                    
                    results.append({
                        'layout_id': layout_id,
                        'size': size,
                        'sample': sample_name,
                        'pdf': str(pdf_path.relative_to(GALLERY_DIR)),
                        'preview': str(preview_path.relative_to(GALLERY_DIR)),
                        'verified': verification.passed if verification else None,
                        'sample_data': sample,
                    })
                    
                    print(f"   ✓ {filename_base}")
                    
                except Exception as e:
                    error_msg = f"   ✗ {filename_base}: {e}"
                    print(error_msg)
                    errors.append({'file': filename_base, 'error': str(e)})
    
    # Generate index.html
    print("\n4. Generating index.html...")
    generate_index_html(results)
    print(f"   ✓ {GALLERY_DIR / 'index.html'}")
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"   PDFs generated:    {pdf_count}")
    print(f"   Previews generated: {webp_count}")
    print(f"   Errors:            {len(errors)}")
    print(f"\n   Gallery: file:///{GALLERY_DIR / 'index.html'}")
    
    if errors:
        print("\nERRORS:")
        for err in errors:
            print(f"   - {err['file']}: {err['error']}")
    
    return pdf_count, webp_count


def generate_index_html(results: list):
    """Generate the HTML gallery index."""
    # Group by layout
    by_layout = {}
    for r in results:
        layout = r['layout_id']
        if layout not in by_layout:
            by_layout[layout] = []
        by_layout[layout].append(r)
    
    # Build filter buttons separately to avoid f-string escaping issues
    filter_buttons = []
    for s in YARD_SIZES:
        filter_buttons.append(f'<button class="filter-btn" onclick="filterSize(\'{s}\')">{s}</button>')
    filter_buttons_html = "".join(filter_buttons)
    
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Yard Sign Render Gallery</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0f172a;
            color: #e2e8f0;
            padding: 2rem;
        }}
        h1 {{ 
            text-align: center; 
            margin-bottom: 1rem;
            color: #f8fafc;
        }}
        .meta {{
            text-align: center;
            color: #94a3b8;
            margin-bottom: 2rem;
        }}
        .layout-section {{
            margin-bottom: 3rem;
        }}
        h2 {{
            color: #4facfe;
            border-bottom: 1px solid #334155;
            padding-bottom: 0.5rem;
            margin-bottom: 1rem;
        }}
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            gap: 1.5rem;
        }}
        .card {{
            background: #1e293b;
            border-radius: 12px;
            overflow: hidden;
            transition: transform 0.2s;
        }}
        .card:hover {{
            transform: translateY(-4px);
        }}
        .card img {{
            width: 100%;
            height: 300px;
            object-fit: contain;
            background: #334155;
        }}
        .card-body {{
            padding: 1rem;
        }}
        .card-title {{
            font-weight: 600;
            margin-bottom: 0.5rem;
        }}
        .card-meta {{
            font-size: 0.85rem;
            color: #94a3b8;
        }}
        .badge {{
            display: inline-block;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 0.75rem;
            margin-right: 4px;
        }}
        .badge-size {{ background: #3b82f6; }}
        .badge-pass {{ background: #22c55e; }}
        .badge-fail {{ background: #ef4444; }}
        a {{ color: #4facfe; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        .filters {{
            text-align: center;
            margin-bottom: 2rem;
        }}
        .filter-btn {{
            background: #334155;
            border: none;
            color: #e2e8f0;
            padding: 8px 16px;
            border-radius: 6px;
            cursor: pointer;
            margin: 0 4px;
        }}
        .filter-btn.active {{
            background: #4facfe;
            color: #0f172a;
        }}
    </style>
</head>
<body>
    <h1>🏠 Yard Sign Render Gallery</h1>
    <p class="meta">Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Total: {len(results)} renders</p>
    
    <div class="filters">
        <button class="filter-btn active" onclick="filterSize('all')">All Sizes</button>
        {filter_buttons_html}
    </div>
'''
    
    for layout, items in by_layout.items():
        html += f'''
    <div class="layout-section">
        <h2>{layout}</h2>
        <div class="grid">
'''
        for item in items:
            verified_badge = ''
            if item['verified'] is True:
                verified_badge = '<span class="badge badge-pass">✓ Verified</span>'
            elif item['verified'] is False:
                verified_badge = '<span class="badge badge-fail">✗ Failed</span>'
            
            html += f'''
            <div class="card" data-size="{item['size']}">
                <a href="{item['pdf']}" target="_blank">
                    <img src="{item['preview']}" alt="{item['sample']}" loading="lazy">
                </a>
                <div class="card-body">
                    <div class="card-title">{item['sample'].replace('_', ' ').title()}</div>
                    <div class="card-meta">
                        <span class="badge badge-size">{item['size']}</span>
                        {verified_badge}
                        <br>
                        <a href="{item['pdf']}" target="_blank">📄 PDF</a>
                    </div>
                </div>
            </div>
'''
        html += '''
        </div>
    </div>
'''
    
    html += '''
    <script>
        function filterSize(size) {
            document.querySelectorAll('.filter-btn').forEach(btn => btn.classList.remove('active'));
            event.target.classList.add('active');
            
            document.querySelectorAll('.card').forEach(card => {
                if (size === 'all' || card.dataset.size === size) {
                    card.style.display = 'block';
                } else {
                    card.style.display = 'none';
                }
            });
        }
    </script>
</body>
</html>
'''
    
    with open(GALLERY_DIR / 'index.html', 'w', encoding='utf-8') as f:
        f.write(html)


if __name__ == '__main__':
    generate_gallery()
