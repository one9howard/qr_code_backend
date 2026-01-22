import os
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.lib import colors

def generate_smart_riser_pdf(order, output_path):
    """
    Generate print-ready PDF for SmartRiser.
    Specs:
      - 2 Pages (Front/Back match)
      - Aluminum only
      - Sizes: 6x24, 6x36
    """
    size_str = order.print_size # e.g. "6x24"
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
    
    # 1. Fetch QR
    from utils.qr_vector import draw_vector_qr
    from database import get_db
    from config import BASE_URL
    
    qr_url = f"{BASE_URL}" 
    payload = order.design_payload or {}
    asset_id = payload.get('sign_asset_id')
    
    if asset_id:
        db = get_db()
        asset = db.execute("SELECT code FROM sign_assets WHERE id = %s", (asset_id,)).fetchone()
        if asset:
            qr_url = f"{BASE_URL}/r/{asset['code']}"

    c = canvas.Canvas(output_path, pagesize=(width + 2*bleed, height + 2*bleed))
    
    def draw_page(c):
        c.saveState()
        c.translate(bleed, bleed)
        
        # White background
        c.setFillColor(colors.white)
        c.rect(0, 0, width, height, fill=1, stroke=0)
        
        # QR Code - Left side
        # Max QR size constrained by height - margin
        qr_size = height * 0.8
        qr_x = height * 0.1 # Padding from left
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
    return output_path
