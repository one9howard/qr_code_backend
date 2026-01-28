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
    '12x18': {
        'safe_margin': to_pt(0.60),
        'smart_v1_minimal': {
            'top_bar': to_pt(0.45),
            'header_band': to_pt(3.20),
            'footer_band': to_pt(2.80),
            'qr_size': to_pt(7.50),
            'qr_padding': to_pt(0.45),
            'fonts': {
                'name': (54, 38), 'phone': (72, 52), 'email': (24, 18), 
                'brokerage': (40, 28), 'cta': (54, 40), 'url': (22, 18)
            }
        },
        'smart_v1_agent_brand': {
            'top_band': to_pt(3.40),
            'footer_band': to_pt(3.60),
            'qr_size': to_pt(7.50),
            'qr_padding': to_pt(0.45),
            'logo_diameter': to_pt(1.40),
            'fonts': {
                'name': (48, 34), 'brokerage': (42, 30), 
                'scan_label': (36, 28), 'cta1': (60, 46), 'cta2': (72, 54), 'url': (22, 18)
            }
        }
    },
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
                'name': (96, 66), 'phone': (120, 88), 'email': (40, 26), 
                'brokerage': (72, 50), 'cta': (96, 72), 'url': (34, 26)
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
    '36x18': {
        'safe_margin': to_pt(0.90),
        'smart_v1_minimal': {
            'top_bar': to_pt(0.55),
            'header_band': to_pt(3.20),
            'footer_band': to_pt(3.20),
            'qr_size': to_pt(10.50),
            'qr_padding': to_pt(0.60),
            'fonts': {
                'name': (72, 50), 'phone': (96, 68), 'email': (30, 22), 
                'brokerage': (52, 34), 'cta': (72, 54), 'url': (28, 22)
            }
        },
        'smart_v1_agent_brand': {
            'top_band': to_pt(3.60),
            'footer_band': to_pt(3.80),
            'qr_size': to_pt(10.50),
            'qr_padding': to_pt(0.60),
            'logo_diameter': to_pt(1.90),
            'fonts': {  # Same as 18x24 Agent Brand
                'name': (64, 44), 'brokerage': (56, 38), 
                'scan_label': (44, 34), 'cta1': (80, 60), 'cta2': (96, 72), 'url': (28, 22)
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
        
        # Legacy fallback sizing
        self.legacy_margin = 0.08 * min(self.width, self.height)
        self.legacy_header_font = max(24, min(72, 0.08 * self.width))
        self.legacy_sub_font = max(18, min(48, 0.04 * self.width))
        self.legacy_cta_font = max(32, min(96, 0.09 * self.width))

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

def draw_fitted_multiline(c, text, x, y_baseline_first, font_name, start_size, min_size, max_width, max_lines=2, align='center', color=None, leading_factor=1.2):
    """
    Fits text into max_lines.
    Returns: (font_size_used, lines_rendered_count, block_height_used)
    """
    if not text: return 0, 0, 0
    if color: c.setFillColorRGB(*hex_to_rgb(color))
    
    # 1. Try single line (prefer largest font)
    c.setFont(font_name, start_size)
    if c.stringWidth(text, font_name, start_size) <= max_width:
        draw_fitted_text(c, text, x, y_baseline_first, font_name, start_size, min_size, max_width, align)
        return start_size, 1, start_size * leading_factor
        
    # 2. Try single line shrunk
    shrunk_size = fit_text_single_line(c, text, font_name, start_size, min_size, max_width)
    if c.stringWidth(text, font_name, shrunk_size) <= max_width:
        # Heuristic: if shrinking > 25% and we allow 2 lines, maybe try wrapping at start_size instead?
        # But user spec says "Try single line at start size -> if overflow shrink -> if still overflow and max_lines==2 wrap"
        # Wait, usually wrapping at a larger font is legibility-preferred over tiny single line.
        # Let's enforce: if shrunk_size < start_size * 0.75 and max_lines > 1, try 2 lines.
        if max_lines == 1 or shrunk_size > (start_size * 0.75):
            draw_fitted_text(c, text, x, y_baseline_first, font_name, start_size, min_size, max_width, align)
            return shrunk_size, 1, shrunk_size * leading_factor

    if max_lines < 2:
         # Force fit single line (ellipsized inside draw_fitted_text)
         draw_fitted_text(c, text, x, y_baseline_first, font_name, start_size, min_size, max_width, align)
         return min_size, 1, min_size * leading_factor

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
                # If single word is too long, we keep it and ellipsize later, or split?
                # For basic logic, keep it.
                
        if current_line:
            lines.append(" ".join(current_line))
            
        if len(lines) <= max_lines:
            # Check if any single line is wider than max_width (e.g. giant word)
            # If so, this size fails unless we ellipsize.
            # But we prefer a size that fits if possible.
            # For now, accept it.
            best_size = test_size
            best_lines = lines
            break
            
        test_size -= 2
        
    # Ellipsize check on final lines
    c.setFont(font_name, best_size)
    final_lines = []
    for line in best_lines:
        if c.stringWidth(line, font_name, best_size) > max_width:
             while len(line) > 3 and c.stringWidth(line + "...", font_name, best_size) > max_width:
                line = line[:-1]
             line += "..."
        final_lines.append(line)
    
    # Draw
    line_height = best_size * leading_factor
    for i, line in enumerate(final_lines):
        # y is baseline of FIRST line. Subsequent lines are lower.
        draw_y = y_baseline_first - (i * line_height)
        
        if align == 'center':
            c.drawCentredString(x, draw_y, line)
        elif align == 'right':
            c.drawRightString(x, draw_y, line)
        else:
            c.drawString(x, draw_y, line)
            
    return best_size, len(final_lines), (len(final_lines) * line_height)


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
        _draw_legacy(c, layout, asset, user_id)
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
    left_w = safe_w * 0.62
    # gap = safe_w * 0.03
    # right_w = safe_w * 0.35
    right_w = safe_w - left_w - (safe_w * 0.03) # Remainder
    
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
    
    # CTA - 60% up from bottom
    cta_y = footer_h * 0.6
    draw_fitted_text(c, cta_text, center_x, cta_y, "Helvetica-Bold", fs[0], fs[1], safe_w, align='center', color=COLORS['base_text'])
    
    # URL
    import urllib.parse
    cleaned = urllib.parse.urlparse(BASE_URL).netloc
    display_url = f"{cleaned}/r/{code}" # Fixed: /r/ added
    
    fs_u = spec['fonts']['url']
    # Ensure it fits above safe bottom
    url_target_y = cta_y - fs[0]
    safe_bottom = l.safe_margin
    if url_target_y < safe_bottom + fs_u[0]:
         url_target_y = safe_bottom + fs_u[0] # Clamp to safe bottom
    
    draw_fitted_text(c, display_url, center_x, url_target_y, "Helvetica", fs_u[0], fs_u[1], safe_w, align='center', color=COLORS['secondary_text'])


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

    # 2. Center: Agent Name
    # Space between circle and right col
    start_x = margin + dia + to_pt(0.25)
    
    # Right column reserve (approx 35% of width or based on safe zone?)
    # Spec says: "Right brokerage name or logo, right-aligned"
    # Let's reserve 35% for brokerage
    right_w = content_w * 0.35
    right_start_x = l.width - margin - right_w
    
    center_w = right_start_x - start_x - to_pt(0.2) # Gutter
    center_mid_x = start_x + (center_w / 2)
    
    name = _read(asset, 'brand_name') or _read(asset, 'agent_name')
    if name:
        fs = spec['fonts']['name']
        draw_fitted_multiline(c, name.upper(), center_mid_x, band_y_center - (fs[0]*0.15), "Helvetica-Bold", fs[0], fs[1], center_w, align='center', color='#ffffff')

    # 3. Right: Brokerage
    brokerage = _read(asset, 'brokerage_name')
    right_align_x = l.width - margin
    
    if brokerage:
        fs = spec['fonts']['brokerage']
        draw_fitted_multiline(c, brokerage, right_align_x, band_y_center - (fs[0]*0.15), "Helvetica", fs[0], fs[1], right_w, align='right', color='#ffffff')

    
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
    
    # Scan Me Label
    fs_lbl = spec['fonts']['scan_label']
    c.setFillColorRGB(*hex_to_rgb(COLORS['base_text']))
    c.setFont("Helvetica", fs_lbl[0])
    c.drawCentredString(l.width/2, qr_y_center + (qr_size/2) + (pad/4), "Scan Me")

    # QR
    code = _read(asset, 'code')
    qr_url = f"{BASE_URL.rstrip('/')}/r/{code}"
    draw_qr(c, qr_url, x=(l.width - qr_size)/2, y=qr_y_center - (qr_size/2), size=qr_size, user_id=user_id)
    

    # --- Footer Band ---
    foot_h = spec['footer_band']
    c.setFillColorRGB(*hex_to_rgb(COLORS['bg_navy']))
    c.rect(-l.bleed, -l.bleed, l.width + 2*l.bleed, foot_h + l.bleed, fill=1, stroke=0)
    
    # Text
    cta1_y = foot_h * 0.65
    cta2_y = foot_h * 0.35
    
    fs1 = spec['fonts']['cta1']
    fs2 = spec['fonts']['cta2']
    
    # Draw "SCAN FOR"
    c.setFont("Helvetica-Bold", fs1[0])
    w_scan = c.stringWidth("SCAN ", "Helvetica-Bold", fs1[0])
    w_for = c.stringWidth("FOR", "Helvetica-Bold", fs1[0])
    total_w = w_scan + w_for
    start_x = (l.width - total_w) / 2
    
    c.setFillColorRGB(1,1,1)
    c.drawString(start_x, cta1_y, "SCAN ")
    c.setFillColorRGB(*hex_to_rgb(accent_hex))
    c.drawString(start_x + w_scan, cta1_y, "FOR")
    
    # Draw "DETAILS"
    c.setFont("Helvetica-Bold", fs2[0])
    c.drawCentredString(l.width/2, cta2_y, "DETAILS")
    
    # URL
    import urllib.parse
    cleaned = urllib.parse.urlparse(BASE_URL).netloc
    display_url = f"{cleaned}/r/{code}" # Fixed: /r/ added
    
    fs_u = spec['fonts']['url']
    c.setFillColorRGB(1,1,1) # White on navy
    
    # Clamp y to safe margin
    url_y = cta2_y - fs2[0] + 10 # heuristic start
    safe_bot = l.safe_margin
    if url_y < safe_bot + fs_u[0]:
        url_y = safe_bot + fs_u[0]
        
    draw_fitted_text(c, display_url, l.width/2, url_y, "Helvetica", fs_u[0], fs_u[1], content_w, align='center', color='#ffffff')


def _draw_legacy(c, l, asset, user_id):
    """Legacy Photo Banner Implementation (Preserved)."""
    # Re-implements original logic but using the 'layout' object context
    # ORIGINAL LOGIC ADAPTED:
    
    # 3. Background
    # Legacy default was solid_blue if not specified
    style_key = _read(asset, 'background_style', 'solid_blue')
    style = STYLE_MAP.get(style_key, STYLE_MAP['solid_blue'])
    
    bg_rgb = hex_to_rgb(style['bg'])
    c.setFillColorRGB(*bg_rgb)
    c.rect(-l.bleed, -l.bleed, l.width + 2*l.bleed, l.height + 2*l.bleed, fill=1, stroke=0)
    
    text_rgb = hex_to_rgb(style['text'])
    
    # 5. Header (Brand Name)
    brand_name = _read(asset, 'brand_name')
    if brand_name:
        c.setFont("Helvetica-Bold", l.legacy_header_font)
        c.setFillColorRGB(*text_rgb)
        c.drawCentredString(l.width/2, l.height - l.legacy_margin - l.legacy_header_font, str(brand_name).upper())

    # 6. Contact Info
    contact_y = l.height - l.legacy_margin - (l.legacy_header_font * 2.2)
    contact_parts = []
    phone = _read(asset, 'phone')
    email = _read(asset, 'email')
    if phone: contact_parts.append(phone)
    if email: contact_parts.append(email)
    
    if contact_parts:
        c.setFont("Helvetica", l.legacy_sub_font)
        c.setFillColorRGB(*text_rgb)
        c.drawCentredString(l.width/2, contact_y, " | ".join(contact_parts))

    # 7. QR
    qr_top = contact_y - (l.legacy_sub_font * 1.5)
    qr_bottom = l.height * 0.25
    qr_max_h = qr_top - qr_bottom
    qr_max_w = l.width - (l.legacy_margin * 2)
    qr_size = min(qr_max_h, qr_max_w, l.width * 0.6)
    
    qr_x = (l.width - qr_size) / 2
    qr_y = qr_bottom + (qr_max_h - qr_size) / 2
    
    # Legacy White Pill
    if style_key in ['solid_blue', 'dark']:
        pad = qr_size * 0.05
        c.setFillColorRGB(1, 1, 1)
        c.roundRect(qr_x - pad, qr_y - pad, qr_size + 2*pad, qr_size + 2*pad, 10, fill=1, stroke=0)

    code = _read(asset, 'code')
    qr_url = f"{BASE_URL.rstrip('/')}/r/{code}"
    draw_qr(c, qr_url, x=qr_x, y=qr_y, size=qr_size, user_id=user_id)

    # 8. CTA
    cta_text = CTA_MAP.get(_read(asset, 'cta_key'), CTA_MAP['scan_for_details'])
    c.setFont("Helvetica-Bold", l.legacy_cta_font)
    c.setFillColorRGB(*text_rgb)
    if style_key == 'light':
        c.setFillColorRGB(*hex_to_rgb(style['accent']))
    c.drawCentredString(l.width/2, l.height * 0.12, cta_text)

    # 9. Corner Images
    def draw_corner_image(key, x, y, size):
        if key and get_storage().exists(key):
            try:
                img_data = get_storage().get_file(key)
                img = ImageReader(img_data)
                c.drawImage(img, x, y, width=size, height=size, mask='auto')
            except: pass

    include_logo = bool(_read(asset, 'include_logo'))
    logo_key = _read(asset, 'agent_logo_key') or _read(asset, 'logo_key')
    if include_logo and logo_key:
        size = l.width * 0.15
        draw_corner_image(logo_key, l.legacy_margin, l.height - l.legacy_margin - size, size)

    include_headshot = bool(_read(asset, 'include_headshot'))
    headshot_key = _read(asset, 'agent_headshot_key') or _read(asset, 'headshot_key')
    if include_headshot and headshot_key:
        size = l.width * 0.15
        draw_corner_image(headshot_key, l.width - l.legacy_margin - size, l.height - l.legacy_margin - size, size)
