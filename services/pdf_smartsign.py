"""
Safe SmartSign PDF Generator (Pro Phase 2).
Generates branded generic signs with NO property details.
"""
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import inch
from reportlab.lib.utils import ImageReader
from reportlab.lib.colors import HexColor
import io
import os
from constants import SIGN_SIZES, DEFAULT_SIGN_SIZE
from utils.pdf_generator import draw_qr
from utils.storage import get_storage
from config import BASE_URL
from services.print_catalog import BANNER_COLOR_PALETTE
import urllib.parse

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

# --- Strict Specs (Points) ---
# 1 inch = 72 pt

def to_pt(inches):
    return inches * 72

SPECS = {
    '18x24': {
        'safe_margin': to_pt(0.75),
        'smart_v1_minimal': {
            'top_bar': to_pt(0.55),
            'header_band': to_pt(4.00),
            'footer_band': to_pt(3.40),
            'qr_size': to_pt(11.00),
            'qr_padding': to_pt(0.55),
            'fonts': {
                'name': (72, 50), 'phone': (96, 68), 'email': (30, 22), 
                'brokerage': (52, 34), 'cta': (72, 54), 'url': (28, 22)
            }
        },
        'smart_v1_photo_banner': {
            'top_band': to_pt(4.50),
            'footer_band': to_pt(4.50),
            'qr_size': to_pt(11.00),
            'qr_padding': to_pt(0.55),
            'headshot_diameter': to_pt(1.90),
            'fonts': {
                'name': (64, 44), 'phone': (48, 36), 'brokerage': (56, 38),
                'cta': (80, 60), 'url': (28, 22)
            }
        },
        'smart_v1_agent_brand': {
            'top_band': to_pt(4.50),
            'footer_band': to_pt(4.50),
            'qr_size': to_pt(11.00),
            'qr_padding': to_pt(0.55),
            'logo_diameter': to_pt(1.90),
            'fonts': {
                'name': (64, 44), 'brokerage': (56, 38), 
                'scan_label': (44, 34), 'cta1': (80, 60), 'cta2': (96, 72), 'url': (28, 22)
            }
        }
    },
    '24x36': {
        'safe_margin': to_pt(1.00),
        'smart_v1_minimal': {
            'top_bar': to_pt(0.70),
            'header_band': to_pt(5.60),
            'footer_band': to_pt(4.80),
            'qr_size': to_pt(15.00),
            'qr_padding': to_pt(0.75),
            'fonts': {
                'name': (96, 66), 'phone': (120, 88), 'email': (40, 28), 
                'brokerage': (72, 50), 'cta': (96, 72), 'url': (34, 26)
            }
        },
        'smart_v1_photo_banner': {
            'top_band': to_pt(6.40),
            'footer_band': to_pt(6.40),
            'qr_size': to_pt(15.00),
            'qr_padding': to_pt(0.75),
            'headshot_diameter': to_pt(2.60),
            'fonts': {
                'name': (86, 60), 'phone': (64, 48), 'brokerage': (76, 54),
                'cta': (110, 80), 'url': (34, 26)
            }
        },
        'smart_v1_agent_brand': {
            'top_band': to_pt(6.40),
            'footer_band': to_pt(6.40),
            'qr_size': to_pt(15.00),
            'qr_padding': to_pt(0.75),
            'logo_diameter': to_pt(2.60),
            'fonts': {
                'name': (86, 60), 'brokerage': (76, 54), 
                'scan_label': (56, 42), 'cta1': (110, 80), 'cta2': (132, 96), 'url': (34, 26)
            }
        }
    },
    '36x24': { # Wide format
        'safe_margin': to_pt(1.00),
        'smart_v1_minimal': {
            'top_bar': to_pt(0.70),
            'header_band': to_pt(4.20),
            'footer_band': to_pt(4.00),
            'qr_size': to_pt(13.00),
            'qr_padding': to_pt(0.70),
            'fonts': {
                'name': (96, 66), 'phone': (120, 88), 'email': (36, 26), 
                'brokerage': (72, 50), 'cta': (96, 72), 'url': (34, 26)
            }
        },
        'smart_v1_photo_banner': {
            'top_band': to_pt(5.00),
            'footer_band': to_pt(5.00),
            'qr_size': to_pt(13.00),
            'qr_padding': to_pt(0.70),
            'headshot_diameter': to_pt(2.40),
            'fonts': {
                'name': (86, 60), 'phone': (64, 48), 'brokerage': (76, 54),
                'cta': (110, 80), 'url': (34, 26)
            }
        },
        'smart_v1_agent_brand': {
            'top_band': to_pt(5.00),
            'footer_band': to_pt(5.00),
            'qr_size': to_pt(13.00),
            'qr_padding': to_pt(0.70),
            'logo_diameter': to_pt(2.40),
            'fonts': { # Same as 24x36 Agent Brand
                'name': (86, 60), 'brokerage': (76, 54), 
                'scan_label': (56, 42), 'cta1': (110, 80), 'cta2': (132, 96), 'url': (34, 26)
            }
        }
    }
}

COLORS = {
    'base_text': '#0f172a',
    'secondary_text': '#475569',
    'rules': '#e2e8f0',
    'bg_minimal': '#ffffff',
    'bg_navy': '#0f172a',
    'cta_fallback': '#cbd5e1'
}

def _read(asset, key, default=None):
    if asset is None:
        return default
    try: return asset[key]
    except: pass
    if isinstance(asset, dict): return asset.get(key, default)
    return getattr(asset, key, default)

def hex_to_rgb(hex_color: str) -> tuple:
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) / 255 for i in (0, 2, 4))

class SmartSignLayout:
    def __init__(self, size_key, layout_id):
        if size_key not in SIGN_SIZES:
            size_key = DEFAULT_SIGN_SIZE
            
        size = SIGN_SIZES[size_key]
        self.width = size['width_in'] * inch
        self.height = size['height_in'] * inch
        self.bleed = 0.125 * inch
        self.size_key = size_key
        self.safe_margin = SPECS.get(self.size_key, SPECS['18x24'])['safe_margin']
        self.layout_spec = SPECS.get(self.size_key, SPECS['18x24']).get(layout_id)
        
        self.layout_spec = SPECS.get(self.size_key, SPECS['18x24']).get(layout_id)

# --- Text Fitting Helpers ---

def fit_text_single_line(c, text, font_name, start_size, min_size, max_width):
    if not text: return min_size
    
    current_size = start_size
    while current_size >= min_size:
        c.setFont(font_name, current_size)
        w = c.stringWidth(text, font_name, current_size)
        if w <= max_width:
            return current_size
        current_size -= 2 # Step down
        
    return min_size # Return min even if it overlaps (ellipsize in draw)

def draw_fitted_text(c, text, x, y, font_name, start_size, min_size, max_width, align='center', color=None):
    if not text: return 0, 0
    if color: c.setFillColorRGB(*hex_to_rgb(color))
    
    final_size = fit_text_single_line(c, text, font_name, start_size, min_size, max_width)
    c.setFont(font_name, final_size)
    
    # Check width one last time to ellipsize if needed
    width = c.stringWidth(text, font_name, final_size)
    if width > max_width:
        # Simple ellipsis logic: verify if chopping chars helps
        while len(text) > 3 and c.stringWidth(text + "...", font_name, final_size) > max_width:
            text = text[:-1]
        text += "..."
        # Recalculate width for alignment if needed, though usually we draw at anchor
        
    if align == 'center':
        c.drawCentredString(x, y, text)
    elif align == 'right':
        c.drawRightString(x, y, text)
    else:
        c.drawString(x, y, text)
        
    return final_size, final_size # return height used (approx cap height? using font size is safer for spacing)

def calculate_fitted_multiline(c, text, font_name, start_size, min_size, max_width, max_lines=2, leading_factor=1.6):
    """
    Calculates best fit for multiline text.
    Returns dict: {'size': int, 'lines': list, 'height': float, 'line_height': float}
    """
    if not text: return {'size': start_size, 'lines': [], 'height': 0, 'line_height': 0}
    
    # 1. Try single line (prefer largest font)
    c.setFont(font_name, start_size)
    if c.stringWidth(text, font_name, start_size) <= max_width:
        return {
            'size': start_size, 
            'lines': [text], 
            'line_height': start_size * leading_factor,
            'height': start_size * leading_factor
        }
        
    # 2. Try single line shrunk
    shrunk_size = fit_text_single_line(c, text, font_name, start_size, min_size, max_width)
    if c.stringWidth(text, font_name, shrunk_size) <= max_width:
        if max_lines == 1 or shrunk_size > (start_size * 0.75):
            return {
                'size': shrunk_size, 
                'lines': [text], 
                'line_height': shrunk_size * leading_factor,
                'height': shrunk_size * leading_factor
            }

    if max_lines < 2:
         return {
            'size': min_size, 
            'lines': [text], # Will be trimmed by draw or caller? draw_fitted_multiline trimmed it.
                             # But calculation usually shouldn't mutate content destructively?
                             # For now, return full text, caller or draw handles ellipsis if width check fails?
                             # No, consistency. Let's return the text.
            'line_height': min_size * leading_factor,
            'height': min_size * leading_factor
         }

    # 3. Try wrapping at start_size, then shrink if needed
    best_size = min_size
    best_lines = [text]
    
    test_size = start_size
    while test_size >= min_size:
        c.setFont(font_name, test_size)
        words = text.split()
        lines = []
        current_line = []
        
        for word in words:
            test_line = " ".join(current_line + [word])
            if c.stringWidth(test_line, font_name, test_size) <= max_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(" ".join(current_line))
                current_line = [word]
                
        if current_line:
            lines.append(" ".join(current_line))
            
        if len(lines) <= max_lines:
            # Check for width overflow of single words?
            # Accepted for now.
            best_size = test_size
            best_lines = lines
            break
            
        test_size -= 2
        
    # Ellipsize check
    c.setFont(font_name, best_size)
    final_lines = []
    for line in best_lines:
        if c.stringWidth(line, font_name, best_size) > max_width:
             while len(line) > 3 and c.stringWidth(line + "...", font_name, best_size) > max_width:
                line = line[:-1]
             line += "..."
        final_lines.append(line)
        
    lh = best_size * leading_factor
    return {
        'size': best_size, 
        'lines': final_lines, 
        'line_height': lh,
        'height': len(final_lines) * lh
    }

def draw_fitted_multiline(c, text, x, y_baseline_first, font_name, start_size, min_size, max_width, max_lines=2, align='center', color=None, leading_factor=1.6):
    """
    Fits and draws text.
    """
    if not text: return 0, 0, 0
    
    # Calculate
    res = calculate_fitted_multiline(c, text, font_name, start_size, min_size, max_width, max_lines, leading_factor)
    
    # Draw
    if color: c.setFillColorRGB(*hex_to_rgb(color))
    c.setFont(font_name, res['size'])
    
    for i, line in enumerate(res['lines']):
        draw_y = y_baseline_first - (i * res['line_height'])
        
        if align == 'center':
            c.drawCentredString(x, draw_y, line)
        elif align == 'right':
            c.drawRightString(x, draw_y, line)
        else:
            c.drawString(x, draw_y, line)
            
    return res['size'], len(res['lines']), res['height']


def _draw_safe_footer_stack(c, l, center_x, cta_text, url_text, cta_font, url_font, max_w, text_color, url_color, cta_lines=1):
    """
    Draws Footer elements stacked BOTTOM-UP from the safe margin.
    Ensures no overlap.
    Stack: Safe Bottom -> URL -> Padding -> CTA
    """
    spec = l.layout_spec
    safe_bottom_y = l.safe_margin
    
    # 1. Measure URL
    url_fs = url_font[0]
    
    url_baseline = safe_bottom_y + (url_fs * 0.4) # ensured lift for descenders
    
    _, _, url_h_used = draw_fitted_multiline(
        c, url_text, center_x, url_baseline, "Helvetica", 
        url_font[0], url_font[1], max_w, max_lines=1, align='center', color=url_color
    )
    
    # 2. CTA
    padding = to_pt(0.25)
    cta_bottom_limit = url_baseline + url_fs + padding
    
    cta_fs = cta_font[0]
    line_height = cta_fs * 1.2
    
    # If wrapped, we need to know how many lines to adjust start Y.
    # We use y_baseline_first.
    # calculate first
    res = calculate_fitted_multiline(
        c, cta_text, "Helvetica-Bold", cta_font[0], cta_font[1], max_w, max_lines=cta_lines
    )
    
    # Height used = res['height']
    # Bottom line baseline is at y_baseline_first - (lines-1)*lh
    # We want Bottom line baseline >= cta_bottom_limit.
    # So y_baseline_first >= cta_bottom_limit + (lines-1)*lh
    
    y_start = cta_bottom_limit + ( (len(res['lines']) - 1) * res['line_height'] )
    
    # Draw
    cta_font_name = "Helvetica-Bold"
    c.setFillColorRGB(*hex_to_rgb(text_color))
    c.setFont(cta_font_name, res['size'])
    
    for i, line in enumerate(res['lines']):
        draw_y = y_start - (i * res['line_height'])
        if i == 0: y_actual_start = draw_y # Debug check
        c.drawCentredString(center_x, draw_y, line)
        
    return 


def generate_smartsign_pdf(asset, order_id=None, user_id=None):
    """
    Generate a branded SmartSign PDF.
    
    Args:
        asset: sign_assets row object (or dict-like). Must include print_size/layout_id context.
        order_id: Optional ID for deterministic output path
        user_id: Optional User ID for QR logo preferences
        
    Returns:
        str: Storage key
    """
    # 1. Extract Config
    # Normalize print size
    size_key = _read(asset, 'print_size') or _read(asset, 'size') or DEFAULT_SIGN_SIZE
    if size_key not in SIGN_SIZES: size_key = DEFAULT_SIGN_SIZE

    # Normalize Layout
    layout_id = _read(asset, 'layout_id', 'smart_v1_minimal')
    if layout_id not in ['smart_v1_minimal', 'smart_v1_agent_brand', 'smart_v1_photo_banner']:
        layout_id = 'smart_v1_minimal'

    layout = SmartSignLayout(size_key, layout_id)
    
    # 2. Setup Canvas
    buffer = io.BytesIO()
    c = canvas.Canvas(
        buffer,
        pagesize=(layout.width + 2*layout.bleed, layout.height + 2*layout.bleed)
    )
    # Origin at bleed corner (0,0 is now the TRIM edge)
    c.translate(layout.bleed, layout.bleed)
    
    # Dispatch
    if layout_id == 'smart_v1_photo_banner':
        _draw_photo_banner(c, layout, asset, user_id)
    elif layout_id == 'smart_v1_agent_brand':
        _draw_agent_brand(c, layout, asset, user_id)
    else:
        # Default to minimal if unknown
        _draw_modern_minimal(c, layout, asset, user_id)
        
    # Finish
    c.showPage()
    c.save()
    buffer.seek(0)
    
    # Storage
    from utils.filenames import make_sign_asset_basename
    basename = make_sign_asset_basename(order_id if order_id else 0, size_key)
    folder = f"pdfs/order_{order_id}" if order_id else "pdfs/tmp_smartsign"
    key = f"{folder}/{basename}_smart.pdf"
    
    storage = get_storage()
    storage.put_file(buffer, key, content_type="application/pdf")
    
    return key


def _draw_modern_minimal(c, l, asset, user_id):
    """Modern Minimal Implementation."""
    spec = l.layout_spec
    
    # Background White
    c.setFillColorRGB(*hex_to_rgb(COLORS['bg_minimal']))
    c.rect(-l.bleed, -l.bleed, l.width + 2*l.bleed, l.height + 2*l.bleed, fill=1, stroke=0)
    
    # --- Top Bar ---
    # Color from Banner Color ID
    color_id = _read(asset, 'banner_color_id') or _read(asset, 'background_style')
    bar_color = BANNER_COLOR_PALETTE.get(color_id, BANNER_COLOR_PALETTE['navy'])
    
    bar_h = spec['top_bar']
    c.setFillColorRGB(*hex_to_rgb(bar_color))
    # Full width including bleed
    c.rect(-l.bleed, l.height - bar_h, l.width + 2*l.bleed, bar_h + l.bleed, fill=1, stroke=0)
    
    # --- Header Band ---
    # Measured layout
    header_h = spec['header_band']
    header_top = l.height - bar_h
    header_bottom = header_top - header_h
    
    # Safe Rect for Header
    safe_top = l.height - l.safe_margin
    safe_left = l.safe_margin
    safe_w = l.width - (2 * l.safe_margin)
    
    # Content Columns
    left_w = safe_w * 0.60
    # gap = safe_w * 0.05
    # right_w = safe_w * 0.35
    right_w = safe_w - left_w - (safe_w * 0.05) # Remainder ensures gap
    
    right_align_x = l.width - l.safe_margin
    
    # 1. Left Column Content Stack (Name -> Phone -> Email)
    # Measure heights first
    name = _read(asset, 'brand_name') or _read(asset, 'agent_name')
    phone = _read(asset, 'phone') or _read(asset, 'agent_phone')
    email = _read(asset, 'email') or _read(asset, 'agent_email')

    # Defaults
    name_h, phone_h, email_h = 0, 0, 0
    name_fs, phone_fs, email_fs = 0, 0, 0
    
    # Measure Name
    if name:
        fs = spec['fonts']['name']
        # Dry run to get height
        # Note: ReportLab canvas is stateful, but dry run helps measure.
        # Just use the draw call and capture return. but we need to know layout first.
        # Actually draw_fitted_multiline logic:
        # We can simulate by calculating.
        # Or simpler: Draw from top-safe down.
        pass

    # New Strategy: Draw from safe_top down, but ensure we center the block if it's small?
    # Spec "Header content is 2-column... Vertical stack strategy".
    # Usually top-aligned relative to the band is safer for predictable alignment with right column?
    # Or vertically centered in the band?
    # Let's align to "visual top" which is usually near safe_top.
    
    cursor_x = safe_left
    cursor_y = min(header_top, safe_top) - to_pt(0.15) # Start below safe top with buffer
    
    # Agent Name
    if name:
        fs = spec['fonts']['name']
        # Font metrics
        # Helvetica cap height approx 0.72 of size. Leading 1.2.
        # We want the CAP of the first line to touch the top cursor?
        # Standard PDF text drawing: y is baseline.
        # If we draw at y, the top of A is approx y + 0.72*size.
        # So baseline should be cursor_y - 0.72*size
        # Let's just use standard padding.
        
        size_used, lines, height = draw_fitted_multiline(c, name.upper(), cursor_x, cursor_y - (fs[0]), "Helvetica-Bold", fs[0], fs[1], left_w, align='left')
        cursor_y -= height
        cursor_y -= (size_used * 0.3) # Padding after block

    # Phone
    if phone:
        fs = spec['fonts']['phone']
        size_used, h_used = draw_fitted_text(c, phone, cursor_x, cursor_y - fs[0], "Helvetica-Bold", fs[0], fs[1], left_w, align='left', color=COLORS['base_text'])
        cursor_y -= (size_used * 1.2) # Leading included in next step? simpler to just move down
        cursor_y -= (size_used * 0.3) # Padding

    # Email
    if email:
        fs = spec['fonts']['email']
        draw_fitted_text(c, email, cursor_x, cursor_y - fs[0], "Helvetica", fs[0], fs[1], left_w, align='left', color=COLORS['secondary_text'])

    # 2. Right Column: Brokerage or Logo
    # Center vertically in the header band?
    mid_y = header_bottom + (header_h / 2)
    
    brokerage_logo_key = _read(asset, 'logo_key') or _read(asset, 'agent_logo_key')
    
    if brokerage_logo_key and get_storage().exists(brokerage_logo_key):
        logo_h = header_h * 0.6
        try:
             img_data = get_storage().get_file(brokerage_logo_key)
             img = ImageReader(img_data)
             iw, ih = img.getSize()
             aspect = iw / ih
             
             draw_w = logo_h * aspect
             draw_h = logo_h
             if draw_w > right_w:
                 draw_w = right_w
                 draw_h = draw_w / aspect
                 
             c.drawImage(img, right_align_x - draw_w, mid_y - (draw_h/2), width=draw_w, height=draw_h, mask='auto')
        except:
             pass 
    else:
        brokerage = _read(asset, 'brokerage_name')
        if brokerage:
            fs = spec['fonts']['brokerage']
            # Estimate height to center
            # Assume 2 lines max
            # Simplification: Draw centered around mid_y?
            # draw_fitted_multiline draws DOWN from y.
            # So y needs to be top baseline.
            # Let's just draw 2 lines centered.
            # If 2 lines: total height ~ 2.2 * size.
            # Start y = mid_y + (1.1 * size) - size?
            # Let's align top of block to mid_y + half_block_height
            
            # Since we don't know final size without fitting, we might need a dry run or just good alignment.
            # Let's align roughly center.
            draw_fitted_multiline(c, brokerage, right_align_x, mid_y + (fs[0] * 0.3), "Helvetica", fs[0], fs[1], right_w, align='right', color=COLORS['secondary_text'])


    # --- QR Code ---
    footer_h = spec['footer_band']
    qr_zone_top = header_bottom
    qr_zone_bot = footer_h
    qr_zone_h = qr_zone_top - qr_zone_bot
    
    center_y = qr_zone_bot + (qr_zone_h / 2)
    center_x = l.width / 2

    qr_size = spec['qr_size']
    pad = spec['qr_padding']
    
    # QR Card (White with Stroke)
    card_size = qr_size + (2 * pad)
    card_x = center_x - (card_size / 2)
    card_y = center_y - (card_size / 2)
    radius = to_pt(0.25)
    
    c.setStrokeColorRGB(*hex_to_rgb(COLORS['rules']))
    c.setLineWidth(2)
    c.setFillColorRGB(1, 1, 1)
    c.roundRect(card_x, card_y, card_size, card_size, radius, fill=1, stroke=1)
    
    # Draw QR
    qr_x = center_x - (qr_size / 2)
    qr_y = center_y - (qr_size / 2)
    code = _read(asset, 'code')
    qr_url = f"{BASE_URL.rstrip('/')}/r/{code}"
    draw_qr(c, qr_url, x=qr_x, y=qr_y, size=qr_size, user_id=user_id)


    # --- Footer ---
    cta_text = CTA_MAP.get(_read(asset, 'cta_key'), 'SCAN FOR DETAILS')
    fs = spec['fonts']['cta']
    
    # URL
    import urllib.parse
    cleaned = urllib.parse.urlparse(BASE_URL).netloc
    display_url = f"{cleaned}/r/{code}"
    fs_u = spec['fonts']['url']
    
    _draw_safe_footer_stack(
        c, l, center_x, 
        cta_text, display_url, 
        fs, fs_u, 
        safe_w, 
        COLORS['base_text'], COLORS['secondary_text'], 
        cta_lines=1
    )


def _draw_agent_brand(c, l, asset, user_id):
    """Agent Brand Implementation."""
    spec = l.layout_spec
    margin = l.safe_margin
    content_w = l.width - 2*margin
    
    # --- Top Band ---
    # Navy Background
    band_h = spec['top_band']
    c.setFillColorRGB(*hex_to_rgb(COLORS['bg_navy']))
    c.rect(-l.bleed, l.height - band_h, l.width + 2*l.bleed, band_h + l.bleed, fill=1, stroke=0)
    
    # Accent Rule
    color_id = _read(asset, 'banner_color_id')
    accent_hex = BANNER_COLOR_PALETTE.get(color_id, COLORS['cta_fallback'])
    if color_id == 'white': accent_hex = COLORS['cta_fallback'] # Fallback if white-on-white
    
    band_y_center = (l.height - band_h) + (band_h / 2)
    
    # 1. Left: Headshot/Logo Circle
    # Diameter
    dia = spec['logo_diameter']
    circle_x = margin + (dia/2)
    circle_y = band_y_center
    
    # Draw Circle Stroke
    c.setStrokeColorRGB(*hex_to_rgb(accent_hex))
    c.setLineWidth(3)
    c.circle(circle_x, circle_y, dia/2, stroke=1, fill=0)
    
    # Image content
    img_key = _read(asset, 'headshot_key') or _read(asset, 'agent_headshot_key') or _read(asset, 'logo_key')
    if img_key and get_storage().exists(img_key):
        # Clip to circle
        p = c.beginPath()
        p.circle(circle_x, circle_y, dia/2)
        c.saveState()
        c.clipPath(p, stroke=0)
        try:
             img_data = get_storage().get_file(img_key)
             img = ImageReader(img_data)
             c.drawImage(img, circle_x - dia/2, circle_y - dia/2, width=dia, height=dia)
        except: pass
        c.restoreState()
    else:
        # Monogram
        initials_list = list(str(_read(asset, 'brand_name') or "A").upper())[:2]
        initials = "".join(initials_list)
        c.setFillColorRGB(1,1,1)
        c.setFont("Helvetica-Bold", dia * 0.5)
        c.drawCentredString(circle_x, circle_y - (dia * 0.15), initials)

    # 2. Name + Brokerage (Safe Vertical Stacking - Task 1 Strict)
    header_bottom = l.height - band_h
    header_safe_top = l.height - margin
    
    content_top = header_safe_top - to_pt(0.15)
    content_bot = header_bottom + to_pt(0.15)
    
    available_h = content_top - content_bot
    if available_h < 0: available_h = 0
    
    start_x = margin + dia + to_pt(0.25)
    available_w = l.width - start_x - margin
    
    # Measurements
    name = _read(asset, 'brand_name') or _read(asset, 'agent_name')
    brokerage = _read(asset, 'brokerage_name')
    
    name_fs = spec['fonts']['name']
    brok_fs = spec['fonts']['brokerage']
    
    # 2.1 Draw Brokerage (Bottom Anchor)
    brok_height_used = 0
    if brokerage:
        # Strict Single Line
        final_size = fit_text_single_line(c, brokerage, "Helvetica", brok_fs[0], brok_fs[1], available_w)
        
        
        # Let's approximate: draw at content_bot + (0.15*size) for decent baseline.
        # This keeps descent roughly inside.
        
        brok_y = content_bot + (final_size * 0.2)
        
        c.setFillColorRGB(*hex_to_rgb(COLORS['base_text'])) # Or white?
        # Agent Brand Header is Navy. So text is White.
        c.setFillColorRGB(1, 1, 1) # White
        # Brokerage often secondary?
        # "Use slightly off-white"
        c.setFillColorRGB(0.9, 0.9, 0.9)
        
        draw_fitted_text(c, brokerage, start_x + (available_w/2), brok_y, "Helvetica", final_size, brok_fs[1], available_w, align='center')
        
        brok_height_used = final_size * 1.5 # Reservation for safety (line height)
    
    # 2.2 Draw Name (Top Anchor)
    if name:
        # Must fit in remaining height?
        # remaining = available_h - brok_height_used
        # Anchor at content_top.
        # draw_fitted_multiline draws DOWN from y_baseline_first.
        # First line CAPS touches content_top?
        # Baseline = content_top - (size * 0.75) typically.
        
        c.setFillColorRGB(1, 1, 1)
        
        # We need to ensure we don't overlap brokerage.
        # Let's limit the height?
        # Real verification checks bounding boxes.
        
        # Let's position name as high as possible (content_top).
        # And brokerage is low.
        
        # We use a leading factor.
        
        # Adjust Y for baseline
        # Standard Helvetica Cap Height ~ 0.72.
        # We want Top of Cap at content_top.
        # So Baseline = content_top - (name_fs[0] * 0.75) roughly.
        
        # But name might shrink.
        # Let's guess start size.
        name_start = name_fs[0]
        y_name = content_top - (name_start * 0.75)
        
        # Draw (Max 2 lines)
        # We assume 1.2 leading.
        draw_fitted_multiline(c, name.upper(), start_x + (available_w/2), y_name, "Helvetica-Bold", name_fs[0], name_fs[1], available_w, max_lines=2, align='center', leading_factor=1.2)


    # 3. Scan Label (Below Header)
    # Must be > header_bottom.
    # Spec says "Scan Me" label sits below header band.
    # Usually in QR area.
    # "Scan Me" label: (44/34).
    # Anchor: just below header?
    
    # header_bottom is the navy band edge.
    # We want it in the white space? Or inside the band?
    # "Center QR zone... Scan Me label" implies it is near QR.
    # If it is inside the band, it would conflict with brokerage?
    # Inspecting spec: "Scan Me" is listed...
    # 24x36: Scan Me (56/42).
    # Wait, where does it go?
    # Usually "Scan Me" is separate from CTA ("Scan For Details").
    # It might be Floating above QR?
    # "Below header_bottom and cannot overlap brokerage".
    # This implies it is OUTSIDE the header band (in the white).
    
    label_txt = "SCAN ME"
    label_fs = spec['fonts']['scan_label']
    
    # Position: Center X. Y = header_bottom - gap?
    # header_bottom is Y=Height-BandH.
    # So Y < header_bottom.
    # Let's put it ~0.5" below header band.
    
    label_y = header_bottom - to_pt(0.75) # Drop down into white
    
    c.setFillColorRGB(*hex_to_rgb(COLORS['base_text']))
    draw_fitted_text(c, label_txt, l.width/2, label_y, "Helvetica-Bold", label_fs[0], label_fs[1], l.width, align='center')



    
    # --- QR Code ---
    qr_size = spec['qr_size']
    pad = spec['qr_padding']
    
    top_of_footer = spec['footer_band']
    bot_of_header = l.height - band_h
    qr_y_center = top_of_footer + ((bot_of_header - top_of_footer) / 2)
    
    card_size = qr_size + (2 * pad)
    radius = to_pt(0.25)
    
    # Card
    c.setStrokeColorRGB(*hex_to_rgb(COLORS['rules']))
    c.setLineWidth(2)
    c.setFillColorRGB(1, 1, 1) # White Card
    c.roundRect((l.width - card_size)/2, qr_y_center - (card_size/2), card_size, card_size, radius, fill=1, stroke=1)
    
    # Scan Me Label (Task C: Remove magic number)
    # Position relative to QR
    # Above QR by padding + half font approx?
    # Logic: center between QR top and header bottom?
    # Or strict offset. Using standard padding.
    
    fs_lbl = spec['fonts']['scan_label']
    scan_y = qr_y_center + (qr_size/2) + pad + (fs_lbl[0] * 0.4) # Just above card
    
    c.setFillColorRGB(*hex_to_rgb(COLORS['base_text']))
    c.setFont("Helvetica", fs_lbl[0])
    c.drawCentredString(l.width/2, scan_y, "Scan Me")

    # QR
    code = _read(asset, 'code')
    qr_url = f"{BASE_URL.rstrip('/')}/r/{code}"
    draw_qr(c, qr_url, x=(l.width - qr_size)/2, y=qr_y_center - (qr_size/2), size=qr_size, user_id=user_id)
    

    # --- Footer Band ---
    foot_h = spec['footer_band']
    c.setFillColorRGB(*hex_to_rgb(COLORS['bg_navy']))
    c.rect(-l.bleed, -l.bleed, l.width + 2*l.bleed, foot_h + l.bleed, fill=1, stroke=0)
    
    # CTA: "SCAN FOR" / "DETAILS" (Task B: No overlap stacking)
    # Stack Bottom-Up:
    # 1. Safe Bottom Margin
    # 2. URL
    # 3. CTA2 (DETAILS)
    # 4. CTA1 (SCAN FOR)
    
    # URL
    import urllib.parse
    cleaned = urllib.parse.urlparse(BASE_URL).netloc
    display_url = f"{cleaned}/r/{code}"
    
    fs_u = spec['fonts']['url']
    fs1 = spec['fonts']['cta1']
    fs2 = spec['fonts']['cta2']
    
    safe_bottom = l.safe_margin
    pad_stack = to_pt(0.25) # Gap between blocks
    
    # 1. Draw URL
    # Align text baseline so descent is covered? 
    # Let's target baseline = safe_bottom + (size*0.3) approx descent
    url_baseline = safe_bottom + (fs_u[0] * 0.35)
    
    # Draw and get explicit height used (if wrapping allowed, but URL is 1 line)
    _, _, url_block_h = draw_fitted_multiline(
        c, display_url, l.width/2, url_baseline, "Helvetica", 
        fs_u[0], fs_u[1], content_w, align='center', color='#ffffff', max_lines=1
    )
    
    # 2. Draw DETAILS (CTA2) above URL
    # Base of CTA2 = Top of URL + padding + descent_of_CTA2?
    # Top of URL approx = url_baseline + (fs_u[0]*0.7)? 
    # Use block height returned. block_height usually covers baseline to ascent + leading.
    # But draw_fitted_multiline returns "lines * line_height".
    # line_height is "size * leading_factor".
    # If we stack: y_next = y_prev_baseline + (prev_height approx?)
    # Better: y_next_baseline = y_prev_baseline + prev_font_size + padding?
    
    # Let's try: 
    # y_url_cap = url_baseline + fs_u[0]
    # y_cta2_baseline = y_url_cap + pad_stack
    
    cta2_baseline = url_baseline + fs_u[0] + pad_stack + (fs2[0]*0.2) # Extra nudges
    
    _, _, cta2_h = draw_fitted_multiline(
        c, "DETAILS", l.width/2, cta2_baseline, "Helvetica-Bold", 
        fs2[0], fs2[1], content_w, align='center', color=accent_hex, max_lines=1
    )
    
    # 3. Draw SCAN FOR (CTA1) above CTA2
    cta1_baseline = cta2_baseline + fs2[0] + pad_stack
    
    # Mixed Color Logic for "SCAN FOR"
    # We measure widths at the resolved font size
    # fit_text_single_line returns *size*
    resolved_fs1 = fit_text_single_line(c, "SCAN FOR", "Helvetica-Bold", fs1[0], fs1[1], content_w)
    
    c.setFont("Helvetica-Bold", resolved_fs1)
    w_scan = c.stringWidth("SCAN ", "Helvetica-Bold", resolved_fs1)
    w_for = c.stringWidth("FOR", "Helvetica-Bold", resolved_fs1)
    total = w_scan + w_for
    start_x = (l.width - total) / 2
    
    c.setFillColorRGB(1,1,1)
    c.drawString(start_x, cta1_baseline, "SCAN ")
    c.setFillColorRGB(*hex_to_rgb(accent_hex))
    c.drawString(start_x + w_scan, cta1_baseline, "FOR")


def _draw_photo_banner(c, l, asset, user_id):
    """Photo Banner Implementation (Strict Spec)."""
    spec = l.layout_spec
    margin = l.safe_margin
    content_w = l.width - 2*margin
    
    # White Base
    c.setFillColorRGB(1,1,1)
    c.rect(-l.bleed, -l.bleed, l.width + 2*l.bleed, l.height + 2*l.bleed, fill=1, stroke=0)
    
    # --- Top Band ---
    band_h = spec['top_band']
    
    # Color
    color_id = _read(asset, 'banner_color_id')
    bg_color = BANNER_COLOR_PALETTE.get(color_id, BANNER_COLOR_PALETTE['navy'])
    if color_id == 'white': bg_color = '#ffffff' # Explicit white
    
    # Draw Band
    c.setFillColorRGB(*hex_to_rgb(bg_color))
    c.rect(-l.bleed, l.height - band_h, l.width + 2*l.bleed, band_h + l.bleed, fill=1, stroke=0)
    
    # Text Colors - Contrast
    is_dark = color_id in ['navy', 'black', 'red', 'green', 'blue', 'orange', 'gray', None]
    text_color = '#ffffff' if is_dark else COLORS['base_text']
    
    band_y_center = (l.height - band_h) + (band_h / 2)
    
    # 1. Left: Headshot Circle
    dia = spec['headshot_diameter']
    circle_x = margin + (dia/2)
    circle_y = band_y_center
    
    # Stroke
    rule_color = COLORS['rules'] if not is_dark else '#ffffff'
    c.setStrokeColorRGB(*hex_to_rgb(rule_color))
    c.setLineWidth(3)
    c.circle(circle_x, circle_y, dia/2, stroke=1, fill=1) # Fill white behind
    
    # Image
    img_key = _read(asset, 'headshot_key') or _read(asset, 'agent_headshot_key')
    if img_key and get_storage().exists(img_key):
        p = c.beginPath()
        p.circle(circle_x, circle_y, dia/2)
        c.saveState()
        c.clipPath(p, stroke=0)
        try:
             img_data = get_storage().get_file(img_key)
             img = ImageReader(img_data)
             c.drawImage(img, circle_x - dia/2, circle_y - dia/2, width=dia, height=dia)
        except: pass
        c.restoreState()
    else:
        # Fallback Monogram or Placeholder
        initials_list = list(str(_read(asset, 'brand_name') or "A").upper())[:2]
        initials = "".join(initials_list)
        c.setFillColorRGB(0.5, 0.5, 0.5)
        c.setFont("Helvetica-Bold", dia * 0.5)
        c.drawCentredString(circle_x, circle_y - (dia * 0.15), initials)
        
    # 2. Right: Brokerage
    brokerage = _read(asset, 'brokerage_name')
    right_w = content_w * 0.40
    right_align_x = l.width - margin
    
    if brokerage:
        fs = spec['fonts']['brokerage']
        # Offset UP to prevent PyMuPDF merging with Left block
        draw_fitted_multiline(c, brokerage, right_align_x, band_y_center - (fs[0]*0.15) + to_pt(0.1), "Helvetica", fs[0], fs[1], right_w, align='right', color=text_color)

    # 3. Center/Left: Name + Phone
    # Space between circle and right col
    start_x = margin + dia + to_pt(0.25)
    end_x = right_align_x - right_w - to_pt(1.0) # Gutter 1.0"
    mid_block_w = end_x - start_x
    
    name = _read(asset, 'brand_name') or _read(asset, 'agent_name')
    phone = _read(asset, 'phone') or _read(asset, 'agent_phone')
    
    if name:
        fs_n = spec['fonts']['name']
        fs_p = spec['fonts']['phone']
        
        # Stack: Name then Phone
        # Vertical align?
        # Calculate strict height.
        # Draw Name top-down from y_center + half_height
        
        # Rough approach: Center the stack on band_y_center
        # We need height of Name + Phone.
        # Assume 1 name 1 phone line -> height approx fs_n + fs_p + gap
        # Or measured.
        
        # Let's align Name Bottom to center? No.
        # Center the bounding box.
        
        # Draw fitted returns height.
        # But we need to draw to know height.
        # Estimate:
        # name_h ~ fs_n*1.2
        # phone_h ~ fs_p*1.2
        # total ~ name_h + phone_h
        
        # start_y = band_y_center + (total/2)
        
        y_cursor = band_y_center + ((fs_n[0]*1.2 + fs_p[0]*1.2)/2) - (fs_n[0]) - to_pt(0.1) # Offset DOWN
        
        # Draw Name
        size, lines, h = draw_fitted_multiline(c, name.upper(), start_x, y_cursor, "Helvetica-Bold", fs_n[0], fs_n[1], mid_block_w, align='left', color=text_color)
        
        y_cursor -= (h + to_pt(0.5))
        
        # Draw Phone
        if phone:
            draw_fitted_text(c, phone, start_x, y_cursor, "Helvetica-Bold", fs_p[0], fs_p[1], mid_block_w, align='left', color=text_color)


    # --- QR Code ---
    qr_size = spec['qr_size']
    pad = spec['qr_padding']
    
    top_of_footer = spec['footer_band']
    bot_of_header = l.height - band_h
    qr_y_center = top_of_footer + ((bot_of_header - top_of_footer) / 2)
    
    card_size = qr_size + (2 * pad)
    radius = to_pt(0.25)
    
    # Card
    c.setStrokeColorRGB(*hex_to_rgb(COLORS['rules']))
    c.setLineWidth(2)
    c.setFillColorRGB(1, 1, 1) # White Card
    c.roundRect((l.width - card_size)/2, qr_y_center - (card_size/2), card_size, card_size, radius, fill=1, stroke=1)
    
    # Draw QR
    code = _read(asset, 'code')
    qr_url = f"{BASE_URL.rstrip('/')}/r/{code}"
    draw_qr(c, qr_url, x=(l.width - qr_size)/2, y=qr_y_center - (qr_size/2), size=qr_size, user_id=user_id)


    # --- Footer Band ---
    foot_h = spec['footer_band']
    c.setFillColorRGB(*hex_to_rgb(bg_color))
    c.rect(-l.bleed, -l.bleed, l.width + 2*l.bleed, foot_h + l.bleed, fill=1, stroke=0)
    
    cta_text = CTA_MAP.get(_read(asset, 'cta_key'), 'SCAN FOR DETAILS')
    display_url = f"{urllib.parse.urlparse(BASE_URL).netloc}/r/{code}"
    
    fs_cta = spec['fonts']['cta']
    fs_url = spec['fonts']['url']
    
    _draw_safe_footer_stack(
        c, l, l.width/2,
        cta_text, display_url,
        fs_cta, fs_url,
        content_w,
        text_color, text_color, # Same color
        cta_lines=1
    )
    # End of Photo Banner (Clean)
