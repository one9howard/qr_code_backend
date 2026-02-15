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
from config import PUBLIC_BASE_URL
import logging
import re
from utils.yard_tokens import SAFE_MARGIN, BLEED, TYPE_SCALE_SERIF, SPACING, QR_MIN_SIZE

logger = logging.getLogger(__name__)
_QR_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{6,128}$")

def _draw_yard_phone_qr_premium(c, layout, address, beds, baths, sqft, price,
                                     agent_name, brokerage, agent_email, agent_phone,
                                     qr_key, agent_photo_key, sign_color, qr_value=None,
                                     agent_photo_path=None, user_id=None, logo_key=None,
                                     license_number=None, state=None, **kwargs):
    """
    Layout L1: Phone + QR Premium.
    Focus: Status, Name, Giant Phone, QR.
    """
    w = layout.width
    h = layout.height
    is_landscape = w > h
    accent_rgb = hex_to_rgb(sign_color)
    COLOR_TEXT = (0.1, 0.1, 0.1)
    status_text = kwargs.get('status_text', "FOR SALE")
    
    c.saveState()
    
    # Common Identity Shim
    asset_shim = {
        'headshot_key': agent_photo_key,
        'agent_name': agent_name,
        'phone': agent_phone,
        'email': agent_email,
        'brokerage': brokerage,
        'logo_key': logo_key
    }

    if not is_landscape:
        # PORTRAIT (18x24)
        # 1. Status Band (Bleed Top)
        status_h = h * 0.12
        c.setFillColorRGB(*accent_rgb)
        c.rect(0, h - status_h, w, status_h, fill=1, stroke=0)
        
        c.setFont(lu.FONT_SERIF, status_h * 0.5)
        c.setFillColorRGB(1, 1, 1)
        c.drawCentredString(w/2, h - status_h * 0.65, status_text.upper())
        
        # 2. Identity Block (Bottom)
        block_h = h * 0.18
        lu.draw_identity_block(c, 0, 0, w, block_h, asset_shim, get_storage(), theme='dark', cta_text="SCAN FOR DETAILS")
        
        # 3. Main Body
        body_top = h - status_h
        body_bottom = block_h
        body_h = body_top - body_bottom
        
        # QR (Upper Middle)
        qr_center_y = body_bottom + (body_h * 0.65)
        qr_size = min(w * 0.55, body_h * 0.4)
        
        url = _resolve_qr_url(qr_value, qr_key)
        _draw_qr_safe(c, url, (w-qr_size)/2, qr_center_y - qr_size/2, qr_size, user_id)
        # Phone (Lower Middle)
        phone_y_center = body_bottom + (body_h * 0.25)
        phone_fmt = lu.format_phone(agent_phone)
        
        c.setFillColorRGB(*accent_rgb)
        pdf_text.draw_single_line_fitted(
            c, phone_fmt, 
            w/2, phone_y_center, 
            w - (2*SAFE_MARGIN),
            lu.FONT_BOLD, w * 0.18, min_font_size=24
        )
    else:
        # LANDSCAPE (36x24) - 3 Columns + Bottom Identity Band
        # Top body: Left = Agent | Center = Status/Phone | Right = QR
        # Bottom: Shared Identity band (CTA lives here)
        strip_h = h * 0.18
        lu.draw_identity_block(
            c, 0, 0, w, strip_h,
            asset_shim, get_storage(),
            theme='dark',
            cta_text="SCAN FOR DETAILS"
        )

        body_h = h - strip_h
        y0 = strip_h
        col_w = w / 3

        # --- Col 3 (Right): QR ---
        qr_size = min(col_w * 0.70, body_h * 0.60)
        qr_center_x = (2.5 * col_w)
        qr_center_y = y0 + (body_h / 2)

        url = _resolve_qr_url(qr_value, qr_key)
        _draw_qr_safe(c, url, qr_center_x - qr_size/2, qr_center_y - qr_size/2, qr_size, user_id)

        # --- Col 2 (Center): Status + Phone ---
        c.setFillColorRGB(*accent_rgb)

        # Status
        c.setFont(lu.FONT_SERIF, body_h * 0.10)
        c.drawCentredString(w/2, y0 + (body_h * 0.72), status_text.upper())

        # Phone
        phone_fmt = lu.format_phone(agent_phone)
        pdf_text.draw_single_line_fitted(
            c, phone_fmt,
            w/2, y0 + (body_h * 0.50),
            col_w * 1.10,
            lu.FONT_BOLD, body_h * 0.16, min_font_size=20
        )

        # --- Col 1 (Left): Agent ---
        photo_size = min(col_w * 0.52, body_h * 0.28)
        photo_x = (col_w - photo_size)/2
        photo_y = y0 + (body_h * 0.60)

        _draw_photo_circle(c, agent_photo_key, photo_x, photo_y, photo_size)

        c.setFillColorRGB(*COLOR_TEXT)
        pdf_text.draw_single_line_fitted(
            c, agent_name,
            col_w/2, photo_y - (body_h * 0.06),
            col_w - SAFE_MARGIN,
            lu.FONT_SCRIPT, body_h * 0.09, min_font_size=14
        )

        pdf_text.draw_single_line_fitted(
            c, brokerage.upper(),
            col_w/2, photo_y - (body_h * 0.14),
            col_w - SAFE_MARGIN,
            lu.FONT_MED, body_h * 0.045, min_font_size=10
        )

        # Separators (body only, above identity band)
        c.setStrokeColorRGB(0.9, 0.9, 0.9)
        c.setLineWidth(1)
        c.line(col_w, y0 + (body_h * 0.10), col_w, y0 + (body_h * 0.92))
        c.line(2*col_w, y0 + (body_h * 0.10), 2*col_w, y0 + (body_h * 0.92))

    c.restoreState()


def _draw_yard_address_qr_premium(c, layout, address, beds, baths, sqft, price,
                                     agent_name, brokerage, agent_email, agent_phone,
                                     qr_key, agent_photo_key, sign_color, qr_value=None,
                                     agent_photo_path=None, user_id=None, logo_key=None,
                                     license_number=None, state=None, **kwargs):
    """
    Layout L2: Address + QR Premium.
    Focus: Address (Serif, Hero), QR.
    """
    w = layout.width
    h = layout.height
    is_landscape = w > h
    accent_rgb = hex_to_rgb(sign_color)
    COLOR_TEXT = (0.1, 0.1, 0.1)
    
    c.saveState()
    
    # Common Identity Shim
    asset_shim = {
        'headshot_key': agent_photo_key,
        'agent_name': agent_name,
        'phone': agent_phone,
        'email': agent_email,
        'brokerage': brokerage,
        'logo_key': logo_key
    }

    if not is_landscape:
        # PORTRAIT
        # Strip Bottom
        strip_h = h * 0.18
        lu.draw_identity_block(c, 0, 0, w, strip_h, asset_shim, get_storage(), theme='dark', cta_text="SCAN FOR DETAILS")
        
        body_h = h - strip_h
        y0 = strip_h
        
        # Address (Top Hero)
        addr_y = y0 + (body_h * 0.80)
        pdf_text.draw_fitted_block(
            c, address.upper(),
            SAFE_MARGIN, addr_y - (body_h * 0.2), # Approx
            w - (2*SAFE_MARGIN), body_h * 0.25,
            lu.FONT_SERIF, body_h * 0.12, min_font_size=TYPE_SCALE_SERIF['address']['min'],
            align='center', max_lines=2
        )
        
        # City/State
        city = kwargs.get('city', '')
        state_val = kwargs.get('state', '')
        if city and state_val:
            pdf_text.draw_single_line_fitted(
                c, f"{city}, {state_val}".upper(),
                w/2, addr_y - (body_h * 0.22),
                w * 0.8,
                lu.FONT_MED, body_h * 0.04, min_font_size=12
            )
        
        # QR (Center Remaining)
        qr_max_y = addr_y - (body_h * 0.25)
        qr_center_y = y0 + ((qr_max_y - y0) / 2)
        qr_size = min(w * 0.6, qr_max_y * 0.6)
        
        url = _resolve_qr_url(qr_value, qr_key)
        _draw_qr_safe(c, url, (w-qr_size)/2, qr_center_y - qr_size/2, qr_size, user_id)
    else:
        # LANDSCAPE (2 Column)
        # Left (60%): Address | Right (40%): QR
        # Bottom: Identity Strip
        strip_h = h * 0.18
        lu.draw_identity_block(c, 0, 0, w, strip_h, asset_shim, get_storage(), theme='dark', cta_text="SCAN FOR DETAILS")
        
        body_h = h - strip_h
        y0 = strip_h
        col_gap = SPACING['lg']
        left_w = (w * 0.6) - col_gap/2
        right_w = (w * 0.4) - col_gap/2
        
        left_x = SAFE_MARGIN
        right_x = SAFE_MARGIN + left_w + col_gap
        
        # Left: Address
        # Vertically center address in body
        addr_y_center = y0 + (body_h / 2)
        
        c.setFillColorRGB(*COLOR_TEXT)
        pdf_text.draw_fitted_block(
            c, address.upper(),
            left_x, addr_y_center - (body_h * 0.15),
            left_w, body_h * 0.3,
            lu.FONT_SERIF, body_h * 0.15, min_font_size=TYPE_SCALE_SERIF['address']['min'],
            align='left', max_lines=2
        )
        
        # Right: QR
        qr_size = min(right_w * 0.8, body_h * 0.8)
        qr_center_x = right_x + (right_w / 2)
        qr_center_y = y0 + (body_h / 2)
        
        url = _resolve_qr_url(qr_value, qr_key)
        _draw_qr_safe(c, url, qr_center_x - qr_size/2, qr_center_y - qr_size/2, qr_size, user_id)
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
    if val:
        return val
    if key:
        token = str(key).strip()
        # Only accept a canonical QR token here; do not derive from storage keys/paths.
        if _QR_TOKEN_RE.fullmatch(token):
            return f"{PUBLIC_BASE_URL.rstrip('/')}/r/{token}"
        logger.warning("[ListingDesigns] Ignoring non-token qr_key fallback input.")
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
