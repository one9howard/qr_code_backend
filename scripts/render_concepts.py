
import os
import sys
import io
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from PIL import Image, ImageDraw

def _safe_image_reader(path: str):
    """Return an ImageReader if path exists, else None."""
    if not path:
        return None
    try:
        if os.path.exists(path):
            return ImageReader(path)
    except Exception:
        return None
    return None


# Add project root to path
sys.path.append(os.getcwd())

# Mock Env
os.environ.setdefault("DATABASE_URL", "postgresql://mock:5432/mock")
os.environ.setdefault("SECRET_KEY", "mock-secret")

from utils.pdf_preview import render_pdf_to_web_preview
from utils.storage import get_storage
from utils.pdf_generator import draw_qr

# Constants
BLEED = 0.125 * inch
WIDTH = 18 * inch
HEIGHT = 24 * inch
HEADSHOT_PATH = os.environ.get("HEADSHOT_PATH", "")  # optional
BROKERAGE_LOGO_PATH = os.environ.get("BROKERAGE_LOGO_PATH", "")  # optional

def setup_canvas():
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=(WIDTH + 2*BLEED, HEIGHT + 2*BLEED))
    c.translate(BLEED, BLEED)
    return c, buffer

def save_and_preview(c, buffer, name):
    c.showPage()
    c.save()
    buffer.seek(0)
    
    storage = get_storage()
    key = f"pdfs/concepts/{name}.pdf"
    storage.put_file(buffer, key, content_type="application/pdf")
    
    # Preview
    preview_key = render_pdf_to_web_preview(key, order_id=99990, sign_size='18x24')
    
    preview_data = storage.get_file(preview_key).getvalue()
    local_path = os.path.join(os.getcwd(), f"concept_{name}.webp")
    with open(local_path, "wb") as f:
        f.write(preview_data)
    print(f"Generated: {local_path}")
    return local_path

def draw_badge_concept():
    c, buf = setup_canvas()
    
    # 1. Split Background
    # Top White (60%), Bottom Navy (40%)
    split_y = HEIGHT * 0.4
    
    # Top White
    c.setFillColor(colors.white)
    c.rect(-BLEED, split_y, WIDTH + 2*BLEED, HEIGHT - split_y + BLEED, fill=1, stroke=0)
    
    # Bottom Navy
    c.setFillColorRGB(15/255, 23/255, 42/255) # Navy
    c.rect(-BLEED, -BLEED, WIDTH + 2*BLEED, split_y + BLEED, fill=1, stroke=0)
    
    # 2. Central Badge (Circular)
    center_x = WIDTH / 2
    center_y = split_y
    badge_dia = 12 * inch
    
    # Badge Fill (Navy) with White Stroke
    c.setFillColorRGB(15/255, 23/255, 42/255)
    c.setStrokeColor(colors.white)
    c.setLineWidth(4)
    c.circle(center_x, center_y, badge_dia/2, fill=1, stroke=1)
    
    # 3. QR Code in Center
    qr_size = 8 * inch
    qr_x = center_x - qr_size/2
    qr_y = center_y - qr_size/2
    
    # Draw White Box behind QR for readability?
    # Or just draw QR white on navy?
    # Standard QR is black on white. 
    # Let's draw a white circle inside badge for QR?
    c.setFillColor(colors.white)
    c.circle(center_x, center_y, qr_size/2 * 1.3, fill=1, stroke=0)
    
    draw_qr(c, "https://insite.co/demo", x=qr_x, y=qr_y, size=qr_size)
    
    # 4. Logo/Headshot in VERY Center of QR (Circular)
    logo_dia = 2.5 * inch
    logo_x = center_x - logo_dia/2
    logo_y = center_y - logo_dia/2
    
    # White circle for logo background to clear QR noise
    c.setFillColor(colors.white)
    c.circle(center_x, center_y, logo_dia/2 + 0.1*inch, fill=1, stroke=0)
    
    if os.path.exists(HEADSHOT_PATH):
        try:
            p = c.beginPath()
            p.circle(center_x, center_y, logo_dia/2)
            c.saveState()
            c.clipPath(p, stroke=0)
            c.drawImage(HEADSHOT_PATH, logo_x, logo_y, width=logo_dia, height=logo_dia, mask='auto')
            c.restoreState()
        except: pass
        
    # 5. Header Text (Top White)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 60)
    c.drawCentredString(center_x, HEIGHT - 3*inch, "FOR SALE")
    c.setFont("Helvetica", 40)
    c.drawCentredString(center_x, HEIGHT - 4*inch, "SCAN FOR PHOTOS & PRICE")
    
    # 6. Footer Text (Bottom Navy)
    # Simulated Riser Look or just text
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 50)
    c.drawCentredString(center_x, 2*inch, "JASON HESTER")
    c.setFont("Helvetica", 40)
    c.drawCentredString(center_x, 1*inch, "(804) 356-0973")
    
    save_and_preview(c, buf, "badge_split")

def draw_modern_round():
    c, buf = setup_canvas()
    
    # Full White
    c.setFillColor(colors.white)
    c.rect(-BLEED, -BLEED, WIDTH+2*BLEED, HEIGHT+2*BLEED, fill=1, stroke=0)
    
    center_x = WIDTH / 2
    
    # Giant Circular Badge (White with Black Border)
    # Replaces unsafe clipping with a scannable inset QR
    qr_y_center = HEIGHT * 0.55
    badge_dia = 12 * inch
    
    # Draw Badge Background & Stroke
    c.setFillColor(colors.white)
    c.setStrokeColor(colors.black)
    c.setLineWidth(5)
    c.circle(center_x, qr_y_center, badge_dia/2, stroke=1, fill=1)
    
    # Safe QR Size (Inscribed Square)
    # D * 0.707 = 8.48, using 8.0 for margin
    qr_size = 8 * inch
    
    # Draw QR (Unclipped)
    # Implicitly H-ECC if we are covering center, though verify draw_qr defaults.
    # Pass ecc_level='H' to be safe since we put a logo on top.
    draw_qr(c, "https://insite.co/demo", x=center_x-qr_size/2, y=qr_y_center-qr_size/2, size=qr_size, ecc_level="H")
    
    # Center Logo
    logo_dia = 3 * inch
    c.setFillColor(colors.white)
    c.circle(center_x, qr_y_center, logo_dia/2 + 0.2*inch, fill=1, stroke=0)
    
    if os.path.exists(HEADSHOT_PATH):
        c.drawImage(HEADSHOT_PATH, center_x-logo_dia/2, qr_y_center-logo_dia/2, width=logo_dia, height=logo_dia, mask='auto', preserveAspectRatio=True)

    # Text
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 80)
    c.drawCentredString(center_x, HEIGHT - 3*inch, "SCAN ME")
    
    # Bottom Branding
    c.setFont("Helvetica", 36)
    c.drawCentredString(center_x, 2*inch, "Powered by InSite")

    save_and_preview(c, buf, "modern_round")

def draw_lux_dark():
    c, buf = setup_canvas()
    
    # Black/Dark Grey
    c.setFillColorRGB(0.1, 0.1, 0.1)
    c.rect(-BLEED, -BLEED, WIDTH+2*BLEED, HEIGHT+2*BLEED, fill=1, stroke=0)
    
    center_x = WIDTH / 2
    
    # Gold Border
    c.setStrokeColorRGB(0.83, 0.68, 0.21) # Gold
    c.setLineWidth(10)
    c.rect(1*inch, 1*inch, WIDTH-2*inch, HEIGHT-2*inch, stroke=1, fill=0)
    
    # QR Code in Gold Frame
    qr_y = HEIGHT / 2 - 4*inch
    qr_size = 10 * inch
    
    c.setFillColor(colors.white) # Base for QR
    c.roundRect(center_x - qr_size/2 - 0.5*inch, qr_y - 0.5*inch, qr_size + 1*inch, qr_size + 1*inch, 20, fill=1, stroke=0)
    
    draw_qr(c, "https://insite.co/demo", x=center_x-qr_size/2, y=qr_y, size=qr_size)
    
    # Text
    c.setFillColorRGB(0.83, 0.68, 0.21) # Gold Text
    c.setFont("Times-Bold", 60)
    c.drawCentredString(center_x, HEIGHT - 3*inch, "EXCLUSIVE VIEWING")
    
    c.setFillColor(colors.white)
    c.setFont("Times-Roman", 30)
    c.drawCentredString(center_x, HEIGHT - 4*inch, "Scan to unlock property details")

    save_and_preview(c, buf, "lux_dark")

def draw_riser_system():
    # Riser attached 
    # Canvas needs to be taller? No, we simulate it within 18x24 or just draw the sign + riser.
    # Let's verify 18x24 main sign + 6x24 riser. Total 24x24 canvas?
    
    w = 24 * inch
    h = 24 * inch # 18 sign + 6 riser
    
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=(w + 2*BLEED, h + 2*BLEED))
    c.translate(BLEED, BLEED)
    
    center_x = w / 2
    
    # Main Sign (Top 18")
    c.setFillColor(colors.white)
    c.rect(0, 6*inch, 24*inch, 18*inch, fill=1, stroke=1)
    
    # Generic Brokerage Branding
    c.setFillColorRGB(0, 0, 0.5) # Navy
    c.setFont("Helvetica-Bold", 80)
    c.drawCentredString(center_x, 18*inch, "ORCHARD REALTY")
    
    # QR
    qr_size = 8 * inch
    draw_qr(c, "https://insite.co/demo", x=center_x - qr_size/2, y=10*inch, size=qr_size)
    c.setFont("Helvetica-Bold", 40)
    c.drawCentredString(center_x, 9*inch, "SCAN FOR PRICE")

    # Riser (Bottom 6")
    # Gap/Hooks simulation
    c.setFillColorRGB(0.9, 0.9, 0.9) # Metal hooks
    c.circle(4*inch, 6*inch, 10, fill=1, stroke=1)
    c.circle(20*inch, 6*inch, 10, fill=1, stroke=1)
    
    # Riser Board
    c.setFillColorRGB(0.8, 0, 0) # Red Riser for contrast
    c.rect(0, 0, 24*inch, 6*inch, fill=1, stroke=1)
    
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 60)
    c.drawCentredString(center_x, 3.5*inch, "JASON HESTER")
    c.setFont("Helvetica", 40)
    c.drawCentredString(center_x, 1.5*inch, "(555) 123-4567")
    
    # Save
    c.showPage()
    c.save()
    buffer.seek(0)
    storage = get_storage()
    key = "pdfs/concepts/riser_system.pdf"
    storage.put_file(buffer, key, content_type="application/pdf")
    
    preview_key = render_pdf_to_web_preview(key, order_id=99991, sign_size='24x24') # Custom size logic might fail? 
    # render_pdf_to_web_preview has hardcoded size lookup.
    # We need to hack it or just rely on fitz detecting size?
    # render_pdf_to_web_preview uses "sign_size" arg to look up SPECS for bleed mostly?
    # Whatever, pass 24x36 for close enough bleed calc or add custom.
    # It calculates DPI based on page rect now (Task A), so it should work regardless of size key!
    
    preview_data = storage.get_file(preview_key).getvalue()
    local_path = os.path.join(os.getcwd(), "concept_riser.webp")
    with open(local_path, "wb") as f:
        f.write(preview_data)
    print(f"Generated: {local_path}")
    return local_path

def run():
    print("Rendering Concepts...")
    draw_badge_concept()
    draw_modern_round()
    draw_lux_dark()
    draw_riser_system()

if __name__ == "__main__":
    run()
