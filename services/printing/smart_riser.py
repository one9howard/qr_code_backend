"""
SmartRiser PDF Generator

Generates print-ready PDFs for SmartRiser products.
Always produces 2 pages (front/back) for double-sided printing.
Returns storage key (not local path).

Specs:
- 2 Pages (Front/Back match)
- Aluminum only
- Sizes: 6x24, 6x36
"""
import io
import logging
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.lib import colors
from database import get_db
from utils.storage import get_storage

logger = logging.getLogger(__name__)


def generate_smart_riser_pdf(order, output_path=None):
    """
    Generate print-ready PDF for SmartRiser.
    
    Args:
        order: Order dict/row object with order data
        output_path: Deprecated - ignored. Returns storage key.
    
    Returns:
        str: Storage key for generated PDF
    """
    storage = get_storage()
    
    # Handle both dict-like and object-like access
    def get_val(obj, key, default=None):
        if hasattr(obj, 'get'):
            return obj.get(key, default)
        return getattr(obj, key, default)
    
    order_id = get_val(order, 'id')
    size_str = get_val(order, 'print_size')
    payload = get_val(order, 'design_payload') or {}
    
    # Parse JSON if needed
    if isinstance(payload, str):
        import json
        payload = json.loads(payload)
    
    if not size_str:
        raise ValueError("Print size missing for SmartRiser")
        
    try:
        w_str, h_str = size_str.lower().split('x')
        width_in = float(w_str)
        height_in = float(h_str)
    except ValueError:
        raise ValueError(f"Invalid size format: {size_str}")

    width = width_in * inch
    height = height_in * inch
    bleed = 0.125 * inch
    
    # Fetch QR URL
    from utils.qr_vector import draw_vector_qr
    from config import BASE_URL
    
    qr_url = f"{BASE_URL}" 
    asset_id = payload.get('sign_asset_id')
    
    if asset_id:
        db = get_db()
        asset = db.execute("SELECT code FROM sign_assets WHERE id = %s", (asset_id,)).fetchone()
        if asset:
            qr_url = f"{BASE_URL}/r/{asset['code']}"

    # Generate PDF in memory
    pdf_buffer = io.BytesIO()
    c = canvas.Canvas(pdf_buffer, pagesize=(width + 2*bleed, height + 2*bleed))
    
    def draw_page(c):
        c.saveState()
        c.translate(bleed, bleed)
        
        # White background
        c.setFillColor(colors.white)
        c.rect(0, 0, width, height, fill=1, stroke=0)
        
        # QR Code - Left side
        qr_size = height * 0.8
        qr_x = height * 0.1
        qr_y = height * 0.1
        
        draw_vector_qr(c, qr_url, x=qr_x, y=qr_y, size=qr_size)
        
        # Text - Centered in remaining space
        c.setFillColor(colors.black)
        
        text_x = (width + qr_x + qr_size) / 2
        text_y = height / 2 - 10
        
        c.setFont("Helvetica-Bold", 72)
        c.drawCentredString(text_x, text_y + 20, "SCAN FOR INFO")
        
        c.setFont("Helvetica", 24)
        code_label = f"SmartRiser {size_str}"
        c.drawCentredString(text_x, text_y - 60, code_label)
        
        c.restoreState()

    # Page 1
    draw_page(c)
    c.showPage()
    
    # Page 2
    draw_page(c)
    c.showPage()
    
    c.save()
    pdf_buffer.seek(0)
    
    # Save to storage
    folder = f"pdfs/order_{order_id}"
    pdf_key = f"{folder}/smart_riser_{size_str}.pdf"
    
    storage.put_file(pdf_buffer, pdf_key, content_type="application/pdf")
    
    return pdf_key
