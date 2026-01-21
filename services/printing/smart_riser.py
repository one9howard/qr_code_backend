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
    
    c = canvas.Canvas(output_path, pagesize=(width, height))
    
    # Simple Content for now (Placeholder logic until real design)
    # Just draw a border and the product name/ID to prove generation
    def draw_page(c):
        c.saveState()
        # White background
        c.setFillColor(colors.white)
        c.rect(0, 0, width, height, fill=1)
        
        # Border
        c.setStrokeColor(colors.black)
        c.setLineWidth(5)
        c.rect(10, 10, width - 20, height - 20)
        
        # Text
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 36)
        text = f"SmartRiser {size_str}"
        c.drawCentredString(width / 2, height / 2, text)
        
        c.setFont("Helvetica", 12)
        c.drawCentredString(width / 2, height / 2 - 40, f"Order: {order.id}")
        
        c.restoreState()

    # Page 1
    draw_page(c)
    c.showPage()
    
    # Page 2
    draw_page(c)
    c.showPage()
    
    c.save()
    return output_path
