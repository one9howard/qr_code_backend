"""
Safe SmartSign PDF Generator (Pro Phase 2).
Generates branded generic signs with NO property details.
"""
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import inch
from reportlab.lib.utils import ImageReader
import io
import os
from constants import SIGN_SIZES, DEFAULT_SIGN_SIZE
from utils.qr_vector import draw_vector_qr
from utils.storage import get_storage
from config import BASE_URL

# Preset CTA texts
CTA_MAP = {
    'scan_for_details': 'SCAN FOR DETAILS',
    'scan_to_view': 'SCAN TO VIEW',
    'scan_for_photos': 'SCAN FOR PHOTOS',
    'scan_to_schedule': 'SCAN TO SCHEDULE',
    'scan_to_connect': 'SCAN TO CONNECT',
    'scan_for_info': 'SCAN FOR INFO',
}

# Color presets (Bg, Text, Accent, QrColor)
STYLE_MAP = {
    'solid_blue':  {'bg': '#0077ff', 'text': '#ffffff', 'accent': '#ffffff'}, # Blue background, white text
    'dark':        {'bg': '#1a1a1a', 'text': '#ffffff', 'accent': '#0077ff'}, # Dark background, white text, blue accent
    'light':       {'bg': '#ffffff', 'text': '#1a1a1a', 'accent': '#0077ff'}, # White background, dark text, blue accent
}

def hex_to_rgb(hex_color: str) -> tuple:
    """Convert hex color to RGB tuple."""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) / 255 for i in (0, 2, 4))

class SmartSignLayout:
    """Simplified layout for SmartSigns."""
    def __init__(self, size_key):
        size = SIGN_SIZES.get(size_key, SIGN_SIZES[DEFAULT_SIGN_SIZE])
        self.width = size['width_in'] * inch
        self.height = size['height_in'] * inch
        self.bleed = 0.125 * inch
        self.margin = 0.08 * min(self.width, self.height)
        
        # Proportional fonts
        self.header_font = max(24, min(72, 0.08 * self.width))
        self.sub_font = max(18, min(48, 0.04 * self.width))
        self.cta_font = max(32, min(96, 0.09 * self.width))

def generate_smartsign_pdf(asset, order_id=None):
    """
    Generate a branded SmartSign PDF.
    
    Args:
        asset: sign_assets row object (or dict-like)
        order_id: Optional ID for deterministic output path
        
    Returns:
        str: Storage key
    """
    # 1. Config extraction
    size_key = "18x24" # Standard MVP size
    layout = SmartSignLayout(size_key)
    
    style_key = getattr(asset, 'background_style', 'solid_blue')
    style = STYLE_MAP.get(style_key, STYLE_MAP['solid_blue'])
    
    cta_key = getattr(asset, 'cta_key', 'scan_for_details')
    cta_text = CTA_MAP.get(cta_key, CTA_MAP['scan_for_details'])
    
    # 2. Setup Canvas
    buffer = io.BytesIO()
    c = canvas.Canvas(
        buffer,
        pagesize=(layout.width + 2*layout.bleed, layout.height + 2*layout.bleed)
    )
    c.translate(layout.bleed, layout.bleed)
    
    # 3. Background
    bg_rgb = hex_to_rgb(style['bg'])
    c.setFillColorRGB(*bg_rgb)
    c.rect(-layout.bleed, -layout.bleed, 
           layout.width + 2*layout.bleed, 
           layout.height + 2*layout.bleed, 
           fill=1, stroke=0)
    
    # 4. Content Colors
    text_rgb = hex_to_rgb(style['text'])
    accent_rgb = hex_to_rgb(style['accent'])
    
    # 5. Header (Brand Name) - Top 15%
    if asset.brand_name:
        c.setFont("Helvetica-Bold", layout.header_font)
        c.setFillColorRGB(*text_rgb)
        c.drawCentredString(layout.width/2, layout.height - layout.margin - layout.header_font, asset.brand_name.upper())

    # 6. Contact Info - Below Brand
    contact_y = layout.height - layout.margin - (layout.header_font * 2.2)
    contact_parts = []
    if asset.phone: contact_parts.append(asset.phone)
    if asset.email: contact_parts.append(asset.email)
    
    if contact_parts:
        c.setFont("Helvetica", layout.sub_font)
        c.setFillColorRGB(*text_rgb)
        c.drawCentredString(layout.width/2, contact_y, " | ".join(contact_parts))

    # 7. QR Code - Center/Large
    # Calculate available space: Below contact, Above CTA
    qr_top = contact_y - (layout.sub_font * 1.5)
    qr_bottom = layout.height * 0.25 # Leave bottom 25% for CTA
    
    qr_max_h = qr_top - qr_bottom
    qr_max_w = layout.width - (layout.margin * 2)
    qr_size = min(qr_max_h, qr_max_w, layout.width * 0.6) # Max 60% width
    
    qr_x = (layout.width - qr_size) / 2
    qr_y = qr_bottom + (qr_max_h - qr_size) / 2
    
    qr_url = f"{BASE_URL.rstrip('/')}/r/{asset.code}"
    
    # Draw Background pill for QR if style is solid color to ensure contrast?
    # Simple rule: If dark background, QR needs white background or be white.
    # Vector QR draws black modules. 
    # Current vector impl assumes dark on light? existing impl draws standard black.
    # ReportLab standard works on white. 
    # For dark backgrounds, we draw a whiterounded rect behind QR.
    if style_key in ['solid_blue', 'dark']:
        pad = qr_size * 0.05
        c.setFillColorRGB(1, 1, 1) # White backing
        c.roundRect(qr_x - pad, qr_y - pad, qr_size + 2*pad, qr_size + 2*pad, 10, fill=1, stroke=0)

    try:
        draw_vector_qr(c, qr_url, qr_x, qr_y, qr_size)
    except Exception as e:
        print(f"[SmartSign] QR Error: {e}")

    # 8. CTA - Bottom
    c.setFont("Helvetica-Bold", layout.cta_font)
    c.setFillColorRGB(*text_rgb)
    # If solid blue, make CTA white. If light, make it blue?
    if style_key == 'light':
        c.setFillColorRGB(*hex_to_rgb(style['accent']))
    
    c.drawCentredString(layout.width/2, layout.height * 0.12, cta_text)

    # 9. Images (Headshot/Logo) - Overlays
    storage = get_storage()
    
    # Helper to draw image
    def draw_corner_image(key, x, y, size):
        if key and storage.exists(key):
            try:
                img_data = storage.get_file(key)
                img = ImageReader(img_data)
                # Aspect ratio preservation could be added here, currently square
                c.drawImage(img, x, y, width=size, height=size, mask='auto')
            except Exception as e:
                print(f"[SmartSign] Image load error {key}: {e}")

    # Logo - Top Left if included
    if asset.include_logo and asset.logo_key:
        size = layout.width * 0.15
        draw_corner_image(asset.logo_key, layout.margin, layout.height - layout.margin - size, size)

    # Headshot - Top Right if included
    if asset.include_headshot and asset.headshot_key:
        size = layout.width * 0.15
        draw_corner_image(asset.headshot_key, layout.width - layout.margin - size, layout.height - layout.margin - size, size)

    # Finish
    c.showPage()
    c.save()
    buffer.seek(0)
    
    # Storage
    from utils.filenames import make_sign_asset_basename
    basename = make_sign_asset_basename(order_id if order_id else 0, size_key)
    # Add branding hash to filename? Not needed if we overwrite or assume order context
    # If order_id provided, store in order folder. Else tmp.
    folder = f"pdfs/order_{order_id}" if order_id else "pdfs/tmp_smartsign"
    key = f"{folder}/{basename}_smart.pdf"
    
    storage = get_storage()
    storage.put_file(buffer, key, content_type="application/pdf")
    
    return key
