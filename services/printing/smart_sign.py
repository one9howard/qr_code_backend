"""SmartSign Generator Service (Strict Templates)

Generates PDFs for SmartSigns using specific versioned layouts.
- Aluminum Only (enforced by catalog/validation, assumed valid here)
- 3 Exact Layouts: smart_v1_photo_banner, smart_v1_minimal, smart_v1_agent_brand
"""
import io
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from services.print_catalog import BANNER_COLOR_PALETTE
from utils.qr_vector import draw_vector_qr
from utils.storage import get_storage
from config import BASE_URL
import os

# --- Constants ---

# Preset Sign Size (SmartSigns are 18x24 MVP)
WIDTH_IN = 18
HEIGHT_IN = 24
BLEED_IN = 0.125

def hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) / 255 for i in (0, 2, 4))

def get_contrast_text_color(hex_bg):
    """Deterministic contrast text color (White or Black)."""
    # Simple brightness heuristic
    rgb = hex_to_rgb(hex_bg)
    brightness = (rgb[0] * 299 + rgb[1] * 587 + rgb[2] * 114) / 1000
    return (0,0,0) if brightness > 0.5 else (1,1,1)

class SmartLayoutCtx:
    def __init__(self):
        self.width = WIDTH_IN * inch
        self.height = HEIGHT_IN * inch
        self.bleed = BLEED_IN * inch
        self.margin = 1.0 * inch # Safe margin

def generate_smart_sign_pdf(db, order):
    """
    Generate PDF for SmartSign order.
    Args:
        db: Connection
        order: Order row/dict
    Returns:
        bytes: PDF content
    """
    layout_id = order.get('layout_id')
    payload = order.get('design_payload', {})
    sides = order.get('sides', 'single')
    
    # Mapping
    render_map = {
        'smart_v1_photo_banner': _render_photo_banner,
        'smart_v1_minimal': _render_minimal,
        'smart_v1_agent_brand': _render_agent_brand
    }
    
    renderer = render_map.get(layout_id)
    if not renderer:
        # Fallback or Error? Phase 5 implies strictness.
        raise ValueError(f"Unknown layout_id: {layout_id}")

    # Prepare Canvas
    buffer = io.BytesIO()
    ctx = SmartLayoutCtx()
    c = canvas.Canvas(buffer, pagesize=(ctx.width + 2*ctx.bleed, ctx.height + 2*ctx.bleed))
    
    # Draw Front
    c.translate(ctx.bleed, ctx.bleed)
    renderer(c, ctx, payload, db, order)
    c.showPage()
    
    # Draw Back (Duplicate)
    if sides == 'double':
        c.translate(ctx.bleed, ctx.bleed)
        renderer(c, ctx, payload, db, order)
        c.showPage()
        
    c.save()
    buffer.seek(0)
    return buffer.read()


# --- Renderers ---

def _draw_qr(c, ctx, qr_x, qr_y, qr_size, order):
    """Draw Vector QR Code linking to property."""
    # Logic to get QR URL.
    # SmartSigns link to a specific asset code.
    # order['sign_asset_id'] -> sign_assets table -> code.
    # BUT Phase 5 might assume we look it up or usage of Design Payload?
    # Actually SmartSigns are assigned to a property later usually? 
    # Or is this "SmartSign Print" which is permanent?
    # "SmartSign offers... SmartSign customization payload... banner_color... agent_name..."
    # If it's a "SmartSign", it needs a QR code that is PERMANENT for the BOARD?
    # Or is it a generic QR?
    # Usually SmartSigns have a unique code per board.
    # We must fetch the associated asset Code.
    
    # Retrieve asset code from order -> sign_asset_id
    asset_id = order.get('sign_asset_id')
    qr_url = "https://insitesigns.com" # Fallback
    
    if asset_id:
        # We need to fetch the asset code. ID provided in order.
        # db passed in _render callers? yes.
        # But 'db' arg in _render functions is needed.
        pass # Handle in caller or helper
        
    # For now, let's assume valid URL generation happens inside _render or passed down.
    # We'll fetch logic inside:
    pass

def _get_qr_url(db, order):
    asset_id = order.get('sign_asset_id')
    if not asset_id:
        return f"{BASE_URL}/" # Should not happen for valid order
    
    # Check if we have the code in order row (joined)? No.
    # Fetch
    row = db.execute("SELECT code FROM sign_assets WHERE id = %s", (asset_id,)).fetchone()
    code = row['code'] if row else 'ERROR'
    return f"{BASE_URL.rstrip('/')}/r/{code}"

def _draw_image(c, storage, key, x, y, w, h, circular=False):
    if not key or not storage.exists(key):
        return
    try:
        img_bytes = storage.get_file(key)
        img = ImageReader(img_bytes)
        c.saveState()
        # Clip if circular? simplified for now
        c.drawImage(img, x, y, width=w, height=h, mask='auto', preserveAspectRatio=True, anchor='c')
        c.restoreState()
    except Exception as e:
        print(f"Image draw error: {e}")


def _render_photo_banner(c, ctx, payload, db, order):
    """
    Layout: 
    - Top: Agent Photo (Left) + Name/Contact (Right)
    - Middle: QR Code (Huge)
    - Bottom: Colored Banner with Brokerage? Or Name?
    Actually "Photo Banner" implies Photo IS the focus or in the banner.
    Let's go with:
    - Top 20%: Banner Color background. Agent Name + Phone in White/Contrast.
    - Middle 60%: QR Code + generic CTA "SCAN FOR INFO"
    - Bottom 20%: Agent Photo (Circle?) / Brokerage.
    
    Wait, let's map to User's Intent of "Photo Banner".
    Likely:
    - Header: Banner Color. Agent Name.
    - Body: QR Code.
    - Overlay: Agent Photo.
    """
    banner_id = payload.get('banner_color_id', 'blue')
    hex_bg = BANNER_COLOR_PALETTE.get(banner_id, '#000000')
    text_color = get_contrast_text_color(hex_bg)
    
    # 1. Top Banner (25% height)
    banner_h = ctx.height * 0.25
    c.setFillColorRGB(*hex_to_rgb(hex_bg))
    c.rect(-ctx.bleed, ctx.height - banner_h, ctx.width + 2*ctx.bleed, banner_h + ctx.bleed, fill=1, stroke=0)
    
    # Agent Name
    c.setFillColorRGB(*text_color)
    c.setFont("Helvetica-Bold", 48)
    name = payload.get('agent_name', '').upper()
    c.drawCentredString(ctx.width/2, ctx.height - (banner_h/2) + 10, name)
    
    # Phone
    c.setFont("Helvetica", 32)
    phone = payload.get('agent_phone', '')
    c.drawCentredString(ctx.width/2, ctx.height - (banner_h/2) - 30, phone)
    
    # 2. QR Code (Center)
    qr_url = _get_qr_url(db, order)
    qr_size = 10 * inch
    qr_x = (ctx.width - qr_size) / 2
    qr_y = (ctx.height - banner_h - qr_size) / 2
    # Draw
    draw_vector_qr(c, qr_url, qr_x, qr_y, qr_size)
    
    # CTA
    c.setFillColorRGB(0,0,0)
    c.setFont("Helvetica-Bold", 36)
    c.drawCentredString(ctx.width/2, qr_y - 50, "SCAN FOR DETAILS")
    
    # 3. Photo (Bottom Left or Overlay?) -> "Photo Banner" 
    # Let's put photo in the banner, Left?
    # If User uploaded headshot.
    storage = get_storage()
    headshot_key = payload.get('agent_headshot_key')
    if headshot_key:
        size = 5 * inch
        # Overlapping bottom of banner
        x = ctx.margin
        y = ctx.height - banner_h - (size/2)
        _draw_image(c, storage, headshot_key, x, y, size, size)


def _render_minimal(c, ctx, payload, db, order):
    """
    Layout:
    - Clean White Background.
    - Large QR Code centered.
    - Bottom strip with simple Agent Name | Phone.
    """
    # 1. QR Code
    qr_url = _get_qr_url(db, order)
    qr_size = 12 * inch
    qr_x = (ctx.width - qr_size) / 2
    qr_y = (ctx.height - qr_size) / 2 + 2*inch
    draw_vector_qr(c, qr_url, qr_x, qr_y, qr_size)
    
    # 2. Bottom Info
    banner_h = 4 * inch
    c.setFont("Helvetica-Bold", 42)
    c.setFillColorRGB(0,0,0)
    
    name = payload.get('agent_name', '')
    phone = payload.get('agent_phone', '')
    
    c.drawCentredString(ctx.width/2, 3*inch, name.upper())
    c.setFont("Helvetica", 32)
    c.drawCentredString(ctx.width/2, 2*inch, phone)
    
    # Logo if present
    storage = get_storage()
    logo_key = payload.get('agent_logo_key')
    if logo_key:
        size = 2 * inch
        _draw_image(c, storage, logo_key, (ctx.width-size)/2, 0.5*inch, size, size)


def _render_agent_brand(c, ctx, payload, db, order):
    """
    Layout:
    - Full color background (Banner Color).
    - White Box for QR code.
    - Agent Info prominent.
    """
    banner_id = payload.get('banner_color_id', 'navy')
    hex_bg = BANNER_COLOR_PALETTE.get(banner_id, '#0f172a')
    text_color = get_contrast_text_color(hex_bg)
    
    # Background
    c.setFillColorRGB(*hex_to_rgb(hex_bg))
    c.rect(-ctx.bleed, -ctx.bleed, ctx.width + 2*ctx.bleed, ctx.height + 2*ctx.bleed, fill=1, stroke=0)
    
    # White Request for QR
    qr_size = 10 * inch
    qr_x = (ctx.width - qr_size) / 2
    qr_y = (ctx.height - qr_size) / 2 + 1*inch
    
    c.setFillColorRGB(1,1,1)
    c.rect(qr_x - 0.5*inch, qr_y - 0.5*inch, qr_size+1*inch, qr_size+1*inch, fill=1, stroke=0)
    
    qr_url = _get_qr_url(db, order)
    draw_vector_qr(c, qr_url, qr_x, qr_y, qr_size)
    
    # Text
    c.setFillColorRGB(*text_color)
    c.setFont("Helvetica-Bold", 56)
    name = payload.get('agent_name', '').upper()
    c.drawCentredString(ctx.width/2, ctx.height - 3*inch, name)
    
    c.setFont("Helvetica", 36)
    phone = payload.get('agent_phone', '')
    c.drawCentredString(ctx.width/2, 2.5*inch, phone)
