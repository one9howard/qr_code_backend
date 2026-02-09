"""
Premium Yard Sign Layouts (V2)
Uses standard typography (Bodoni, Allura) and components.
"""
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib.colors import HexColor

import services.printing.layout_utils as lu
import utils.pdf_text as pdf_text
from utils.pdf_generator import hex_to_rgb, draw_qr, LayoutSpec
from utils.storage import get_storage
from config import BASE_URL
import os

def _draw_yard_phone_qr_premium(c, layout, address, beds, baths, sqft, price,
                                     agent_name, brokerage, agent_email, agent_phone,
                                     qr_key, agent_photo_key, sign_color, qr_value=None,
                                     agent_photo_path=None, user_id=None, logo_key=None,
                                     license_number=None, state=None, **kwargs):
    """
    Layout L1: Phone + QR Premium.
    Focus: Status, Name, Giant Phone, QR.
    """
    # Dimensions
    w = layout.width
    h = layout.height
    is_landscape = w > h
    
    # Colors
    accent_rgb = hex_to_rgb(sign_color)
    COLOR_TEXT = (0.1, 0.1, 0.1)
    
    # --- STATUS HEADLINE (Top) ---
    # e.g. "FOR SALE" - Bodoni (Serif)
    # We don't have explicit status passed in args usually? 
    # Listing Signs often default to "FOR SALE" or use listing status.
    # We will hardcode "FOR SALE" or valid status if passed (kwargs?).
    status_text = kwargs.get('status_text', "FOR SALE")
    
    c.saveState()
    
    if not is_landscape:
        # PORTRAIT (18x24)
        # Stack: Status | QR | Phone | Agent
        
        # 1. Status (Top Band)
        status_h = h * 0.12
        c.setFillColorRGB(*accent_rgb)
        c.rect(0, h - status_h, w, status_h, fill=1, stroke=0)
        
        c.setFont(lu.FONT_SERIF, status_h * 0.5)
        c.setFillColorRGB(1, 1, 1)
        c.drawCentredString(w/2, h - status_h * 0.65, status_text.upper())
        
        # 2. QR Code (Upper Middle)
        qr_y_center = h * 0.65
        qr_size = w * 0.55
        qr_x = (w - qr_size) / 2
        qr_y = qr_y_center - (qr_size / 2)
        
        # Resolve QR URL
        url = _resolve_qr_url(qr_value, qr_key)
        _draw_qr_safe(c, url, qr_x, qr_y, qr_size, user_id)
        
        # CTA
        c.setFillColorRGB(*COLOR_TEXT)
        pdf_text.draw_single_line_fitted(
            c, "Scan for details", 
            w/2, qr_y - (w * 0.08), 
            w * 0.8,
            lu.FONT_SCRIPT, w * 0.08, min_font_size=12
        )
        
        # 3. Giant Phone (Lower Middle)
        phone_y_center = h * 0.35
        phone_fmt = lu.format_phone(agent_phone)
        
        # Fits HUGE
        c.setFillColorRGB(*accent_rgb)
        pdf_text.draw_single_line_fitted(
            c, phone_fmt, 
            w/2, phone_y_center, 
            w * 0.95,
            lu.FONT_BOLD, w * 0.18, min_font_size=24
        )
        
        # 4. Agent Identity (Bottom)
        # Use Identity Block
        # It needs about 15-20% height
        block_h = h * 0.18
        # Pass asset dict shim
        asset_shim = {
            'headshot_key': agent_photo_key,
            'agent_name': agent_name,
            'phone': agent_phone, # Redundant but part of block
            'email': agent_email,
            'brokerage': brokerage,
            'logo_key': logo_key
        }
        lu.draw_identity_block(c, 0, 0, w, block_h, asset_shim, get_storage(), theme='dark')
        
    else:
        # LANDSCAPE (36x24) or Split
        # Left: Agent/Status/Phone. Right: QR.
        # Strict user req: "L1: Left agent block, Center phone..., Right QR"
        # 3 Columns?
        
        col_w = w / 3
        
        # Col 1: Agent Block (Full Height? Or Top?)
        # User: "Left: agent block... Center: phone... Right: QR"
        # This implies vertical columns.
        
        # Functionality:
        # Col 1 (Left): Agent Info + Headshot
        # Col 2 (Center): Status + Giant Phone
        # Col 3 (Right): QR + CTA
        
        # Let's try to frame it nicely.
        
        # Col 3: QR
        qr_size = min(col_w * 0.8, h * 0.6)
        qr_x = (2 * col_w) + (col_w - qr_size)/2
        qr_y = (h - qr_size)/2 + (h * 0.05)
        
        url = _resolve_qr_url(qr_value, qr_key)
        _draw_qr_safe(c, url, qr_x, qr_y, qr_size, user_id)
        
        # CTA
        c.setFillColorRGB(*COLOR_TEXT)
        pdf_text.draw_single_line_fitted(
            c, "Scan for details",
            qr_x + qr_size/2, qr_y - (h * 0.08),
            col_w * 0.9,
            lu.FONT_SCRIPT, h * 0.06, min_font_size=12
        )
        
        # Col 2: Status + Phone
        c.setFillColorRGB(*accent_rgb)
        c.setFont(lu.FONT_SERIF, h * 0.08)
        c.drawCentredString(w/2, h * 0.7, status_text.upper())
        
        phone_fmt = lu.format_phone(agent_phone)
        pdf_text.draw_single_line_fitted(
            c, phone_fmt,
            w/2, h * 0.5,
            col_w * 1.2, # Use more space since it's centered
            lu.FONT_BOLD, h * 0.12, min_font_size=20
        )
        
        # License line?
        if license_number:
            _draw_license_line(c, w/2, h * 0.4, license_number, state, align='center')

        # Col 1: Agent
        # We can reuse Identity Block but it's horizontal.
        # Custom draw for vertical left column.
        
        photo_size = min(col_w * 0.6, h * 0.3)
        photo_x = (col_w - photo_size)/2
        photo_y = h * 0.55
        
        # Draw Photo
        _draw_photo_circle(c, agent_photo_key, photo_x, photo_y, photo_size)
        
        # Name
        c.setFillColorRGB(*COLOR_TEXT)
        pdf_text.draw_single_line_fitted(
            c, agent_name,
            col_w/2, photo_y - (h*0.06),
            col_w * 0.9,
            lu.FONT_SCRIPT, h * 0.07, min_font_size=14
        )
        
        # Brokerage below
        pdf_text.draw_single_line_fitted(
            c, brokerage.upper(),
            col_w/2, photo_y - (h*0.12),
            col_w * 0.9,
            lu.FONT_MED, h * 0.035, min_font_size=10
        )
        
        # Separators
        c.setStrokeColorRGB(0.9, 0.9, 0.9)
        c.setLineWidth(2)
        c.line(col_w, h*0.1, col_w, h*0.9)
        c.line(2*col_w, h*0.1, 2*col_w, h*0.9)


    c.restoreState()


def _draw_yard_address_qr_premium(c, layout, address, beds, baths, sqft, price,
                                     agent_name, brokerage, agent_email, agent_phone,
                                     qr_key, agent_photo_key, sign_color, qr_value=None,
                                     agent_photo_path=None, user_id=None, logo_key=None,
                                     license_number=None, state=None, **kwargs):
    """
    Layout L2: Address + QR Premium.
    Focus: Address (Serif), QR, Bottom Strip.
    """
    w = layout.width
    h = layout.height
    is_landscape = w > h
    accent_rgb = hex_to_rgb(sign_color)
    COLOR_TEXT = (0.1, 0.1, 0.1)
    
    c.saveState()
    
    # Bottom Strip (Agent) - Same for both orientations usually
    strip_h = h * 0.18
    asset_shim = {
        'headshot_key': agent_photo_key,
        'agent_name': agent_name,
        'phone': agent_phone,
        'email': agent_email,
        'brokerage': brokerage,
        'logo_key': logo_key
    }
    lu.draw_identity_block(c, 0, 0, w, strip_h, asset_shim, get_storage(), theme='dark')
    
    # Body Area
    body_h = h - strip_h
    
    # Address Block
    # Top 30% of body
    addr_y = body_h * 0.85
    
    city = kwargs.get('city', '')
    state_val = kwargs.get('state', '') # This is property state
    
    c.setFillColorRGB(*COLOR_TEXT)
    
    # Fit Address (Serif)
    # Allow 2 lines if needed using draw_fitted_block?
    # User said "Giant Address".
    # draw_fitted_block calculates Y from center, so we need to be careful with positioning.
    # Let's define a box
    
    addr_box_h = body_h * 0.25
    addr_box_y = body_h - addr_box_h - (body_h * 0.05)
    
    pdf_text.draw_fitted_block(
        c, address.upper(),
        w * 0.05, addr_box_y, w * 0.9, addr_box_h,
        lu.FONT_SERIF, body_h * 0.15, min_font_size=24,
        max_lines=2
    )
    
    # City/State
    sub_y = addr_box_y - (body_h * 0.02)
    if city and state_val:
        sub_txt = f"{city}, {state_val}"
        pdf_text.draw_single_line_fitted(
            c, sub_txt.upper(),
            w/2, sub_y,
            w * 0.8,
            lu.FONT_MED, body_h * 0.05, min_font_size=12
        )
    
    # QR Code (Center of remaining space)
    remaining_top = sub_y - (body_h * 0.05)
    remaining_h = remaining_top
    
    qr_size = min(w * 0.5, remaining_h * 0.7)
    qr_x = (w - qr_size) / 2
    
    # Center vertically in remaining space
    qr_y = (remaining_h - qr_size) / 2
    
    url = _resolve_qr_url(qr_value, qr_key)
    _draw_qr_safe(c, url, qr_x, qr_y, qr_size, user_id)
    
    # CTA
    c.setFillColorRGB(*COLOR_TEXT)
    pdf_text.draw_single_line_fitted(
        c, "Scan for details",
        w/2, qr_y - (qr_size * 0.15),
        w * 0.8,
        lu.FONT_SCRIPT, qr_size * 0.15, min_font_size=12
    )
    
    # License Line
    if license_number:
        # Place above strip
        _draw_license_line(c, w/2, strip_h + 10, license_number, state, align='center')

    c.restoreState()


def _draw_open_house_gold(c, layout, address, beds, baths, sqft, price,
                         agent_name, brokerage, agent_email, agent_phone,
                         qr_key, agent_photo_key, sign_color, qr_value=None,
                         agent_photo_path=None, user_id=None, logo_key=None,
                         license_number=None, state=None, **kwargs):
    """
    Layout L3: Open House / Gold Event Style.
    Based on Design #2: Gold/Black/White, "OPEN HOUSE" header.
    """
    w = layout.width
    h = layout.height
    is_landscape = w > h
    
    # Colors
    GOLD = (0.85, 0.65, 0.13) # Gold-ish
    BLACK = (0, 0, 0)
    WHITE = (1, 1, 1)
    
    c.saveState()
    
    # 1. Header Bar (Gold) - "OPEN HOUSE"
    header_h = h * 0.22
    c.setFillColorRGB(*GOLD)
    c.rect(0, h - header_h, w, header_h, fill=1, stroke=0)
    
    # Header Text (White, Bold, Boxed?)
    # Image 2 had a box. Let's do a Black Box inside the Gold strip.
    box_margin = header_h * 0.15
    # Fix: Ensure box isn't too wide if w is small
    c.setFillColorRGB(*BLACK)
    c.rect(w * 0.1, h - header_h + box_margin, w * 0.8, header_h - (2*box_margin), fill=1, stroke=0)
    
    c.setFillColorRGB(*WHITE)
    c.setFont(lu.FONT_BOLD, header_h * 0.5)
    c.drawCentredString(w/2, h - header_h * 0.65 + box_margin, "OPEN HOUSE")
    
    # 2. Main Body
    if is_landscape:
        # Left Strip (Black): "FOR SALE"
        strip_w = w * 0.35
        c.setFillColorRGB(*BLACK)
        c.rect(0, 0, strip_w, h - header_h, fill=1, stroke=0)
        
        # QR Code (White Box inside Black Strip)
        qr_size = strip_w * 0.7
        qr_x = (strip_w - qr_size)/2
        qr_y = (h - header_h) * 0.55
        
        # White backing for QR
        c.setFillColorRGB(*WHITE)
        c.rect(qr_x - 5, qr_y - 5, qr_size + 10, qr_size + 10, fill=1, stroke=0)
        
        url = _resolve_qr_url(qr_value, qr_key)
        _draw_qr_safe(c, url, qr_x, qr_y, qr_size, user_id)
        
        # "FOR SALE" Text below QR in Yellow/Gold
        c.setFillColorRGB(*GOLD)
        c.setFont(lu.FONT_BOLD, strip_w * 0.22)
        # Stacked "FOR" "SALE"
        c.drawCentredString(strip_w/2, qr_y - (strip_w * 0.3), "FOR")
        c.drawCentredString(strip_w/2, qr_y - (strip_w * 0.55), "SALE")

        # Right Area (Gold background)
        right_x = strip_w
        right_w = w - strip_w
        
        c.setFillColorRGB(*GOLD)
        c.rect(right_x, 0, right_w, h - header_h, fill=1, stroke=0)
        
        # Phone Number (Huge, Black)
        phone_fmt = lu.format_phone(agent_phone)
        c.setFillColorRGB(*BLACK)
        
        # Fit phone
        # Ensure we have lu available or passed
        p_size = lu.fit_text_one_line(c, phone_fmt, lu.FONT_BOLD, right_w * 0.9, (h-header_h)*0.3, (h-header_h)*0.15)
        c.setFont(lu.FONT_BOLD, p_size)
        c.drawCentredString(right_x + right_w/2, (h-header_h) * 0.2, phone_fmt)
        
        # Agent Name / Email (Small above phone)
        c.setFillColorRGB(*BLACK)
        c.setFont(lu.FONT_MED, right_w * 0.05)
        c.drawCentredString(right_x + right_w/2, (h-header_h) * 0.55, agent_name.upper())

    else:
        # Portrait fallback
        c.setFillColorRGB(*BLACK)
        c.setFont(lu.FONT_BOLD, w*0.1)
        c.drawCentredString(w/2, h/2, "Landscape Only")

    c.restoreState()


# --- Helpers ---

def _resolve_qr_url(val, key):
    if val: return val
    if key:
        return f"{BASE_URL.rstrip('/')}/r/{os.path.basename(key).split('.')[0]}"
    return "https://example.com"

def _draw_qr_safe(c, url, x, y, size, uid):
    try:
        draw_qr(c, url, x, y, size, ecc_level="H", user_id=uid)
    except Exception:
        # Fallback rect
        c.setFillColorRGB(0,0,0)
        c.rect(x, y, size, size)

def _draw_photo_circle(c, key, x, y, size):
    storage = get_storage()
    if key and storage.exists(key):
        try:
            c.saveState()
            p = c.beginPath()
            p.circle(x + size/2, y + size/2, size/2)
            c.clipPath(p, stroke=0)
            img = ImageReader(storage.get_file(key))
            c.drawImage(img, x, y, width=size, height=size)
            c.restoreState()
            # Stroke
            c.setStrokeColorRGB(0.8, 0.8, 0.8)
            c.setLineWidth(1)
            c.circle(x + size/2, y + size/2, size/2, stroke=1, fill=0)
        except: pass

def _draw_license_line(c, x, y, num, state, align='center'):
    # Logic: CA -> "DRE #..."
    label = "Lic #"
    if state == 'CA':
        label = "DRE #"
    txt = f"{label} {num}"
    
    c.setFillColorRGB(0.5, 0.5, 0.5)
    c.setFont(lu.FONT_MED, 10) # Small
    if align == 'center':
        c.drawCentredString(x, y, txt)
    elif align == 'right':
        c.drawRightString(x, y, txt)
    else:
        c.drawString(x, y, txt)
