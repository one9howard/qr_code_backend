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
from config import BASE_URL, PUBLIC_BASE_URL
from services.print_catalog import BANNER_COLOR_PALETTE
from services.printing.layout_utils import (
    register_fonts, 
    draw_identity_block, 
    fit_text_one_line, 
    FONT_BODY, FONT_MED, FONT_BOLD
)
import urllib.parse

# Preset CTA texts (Benefit Driven Check)
CTA_MAP = {
    'scan_for_details': 'SCAN FOR PHOTOS & PRICE',
    'scan_to_view': 'SCAN TO VIEW LISTING',
    'scan_for_photos': 'SCAN FOR PHOTOS',
    'scan_to_schedule': 'SCAN TO SCHEDULE TOUR',
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

from services.specs import SMARTSIGN_V1_MINIMAL_SPECS, GLOBAL_PRINT_RULES

# Helper to build SPECS dynamically
SPECS = {
    '18x24': {
        'smart_v1_photo_banner': {
            'top_band': to_pt(4.50),
            'footer_band': to_pt(4.50),
            'qr_size': to_pt(11.00),
            'qr_padding': to_pt(0.55),
            'headshot_diameter': to_pt(1.90),
            'fonts': { # Legacy Photo Banner Metrics (still using Helvetica or mapped?)
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
    '36x24': {
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
            'fonts': {
                'name': (86, 60), 'brokerage': (76, 54), 
                'scan_label': (56, 42), 'cta1': (110, 80), 'cta2': (132, 96), 'url': (34, 26)
            }
        }
    }
}

# Dynamic Injection: Smart V1 Minimal (Canonical)
_min_specs = SMARTSIGN_V1_MINIMAL_SPECS['sizes']
_safe_margins = GLOBAL_PRINT_RULES['safe_margin_in']

for size, s_data in _min_specs.items():
    if size not in SPECS:
         continue
         
    # 1. Global Safe Margin
    SPECS[size]['safe_margin'] = to_pt(_safe_margins[size])
    
    # 2. Minimal Layout
    SPECS[size]['smart_v1_minimal'] = {
        'top_bar': to_pt(s_data['accent_rule_h_in']),
        'header_band': to_pt(s_data['header_h_in']),
        'footer_band': to_pt(s_data['footer_h_in']),
        'qr_size': to_pt(s_data['qr']['qr_size_in']),
        'qr_padding': to_pt(s_data['qr']['card_pad_in']),
        'fonts': s_data['fonts']
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


# --- Replaced by fit_text_one_line ---
# Keeping helpers if needed for legacy calculate_fitted_multiline, 
# although layout_utils now handles most of this.
# For minimal touch refactor, we retain local multiline helpers but update FONTS.

def calculate_fitted_multiline(c, text, font_name, start_size, min_size, max_width, max_lines=2, leading_factor=1.6):
    """
    Legacy multiline calculator, updated to respect Inter fonts passed in.
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
        
    # 2. Try single line shrunk (using layout_utils fit logic manually here)
    shrunk_size = fit_text_one_line(c, text, font_name, max_width, start_size, min_size)
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
            'lines': [text], 
            'line_height': min_size * leading_factor,
            'height': min_size * leading_factor
         }

    # 3. Try wrapping
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
            best_size = test_size
            best_lines = lines
            break
            
        test_size -= 2
        
    lh = best_size * leading_factor
    return {
        'size': best_size, 
        'lines': best_lines, 
        'line_height': lh,
        'height': len(best_lines) * lh
    }

def draw_fitted_multiline(c, text, x, y_baseline_first, font_name, start_size, min_size, max_width, max_lines=2, align='center', color=None, leading_factor=1.6):
    if not text: return 0, 0, 0
    res = calculate_fitted_multiline(c, text, font_name, start_size, min_size, max_width, max_lines, leading_factor)
    
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
    Footer Stack: CTA + Short URL
    """
    # Use Global Fonts
    spec = l.layout_spec
    safe_bottom_y = l.safe_margin
    
    # 1. Measure URL
    url_fs = url_font[0]
    # url_baseline = safe_bottom_y + (url_fs * 0.4) 
    # Use PUBLIC_BASE_URL for print
    
    _, _, url_h_used = draw_fitted_multiline(
        c, url_text, center_x, safe_bottom_y + url_fs, FONT_BODY, 
        url_font[0], url_font[1], max_w, max_lines=1, align='center', color=url_color
    )
    
    # 2. CTA
    padding = to_pt(0.25)
    cta_bottom_limit = safe_bottom_y + url_fs + padding + url_fs # Push up more
    
    # Reuse multiline fitting
    res = calculate_fitted_multiline(
        c, cta_text, FONT_BOLD, cta_font[0], cta_font[1], max_w, max_lines=cta_lines
    )
    
    y_start = cta_bottom_limit + ( (len(res['lines']) - 1) * res['line_height'] )
    
    c.setFillColorRGB(*hex_to_rgb(text_color))
    c.setFont(FONT_BOLD, res['size'])
    
    for i, line in enumerate(res['lines']):
        draw_y = y_start - (i * res['line_height'])
        c.drawCentredString(center_x, draw_y, line)
        
    return 


def generate_smartsign_pdf(asset, order_id=None, user_id=None):
    # 0. Register Fonts
    register_fonts()

    # 1. Extract Config
    size_key = _read(asset, 'print_size') or _read(asset, 'size') or DEFAULT_SIGN_SIZE
    if size_key not in SIGN_SIZES: size_key = DEFAULT_SIGN_SIZE

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
    c.translate(layout.bleed, layout.bleed)
    
    # Dispatch
    if layout_id == 'smart_v1_photo_banner':
        _draw_photo_banner(c, layout, asset, user_id)
    elif layout_id == 'smart_v1_agent_brand':
        _draw_agent_brand(c, layout, asset, user_id)
    else:
        _draw_modern_minimal(c, layout, asset, user_id)
        
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
    """Modern Minimal with Shared Identity Block."""
    spec = l.layout_spec
    
    # Background White
    c.setFillColorRGB(*hex_to_rgb(COLORS['bg_minimal']))
    c.rect(-l.bleed, -l.bleed, l.width + 2*l.bleed, l.height + 2*l.bleed, fill=1, stroke=0)
    
    # --- Header Band (Now using Shared Block) ---
    header_h = spec['header_band']
    header_top_y = l.height - spec['top_bar'] # Below top accent bar
    band_y = header_top_y - header_h
    
    # Accent Bar
    color_id = _read(asset, 'banner_color_id') or _read(asset, 'background_style')
    bar_color = BANNER_COLOR_PALETTE.get(color_id, BANNER_COLOR_PALETTE['navy'])
    c.setFillColorRGB(*hex_to_rgb(bar_color))
    c.rect(-l.bleed, header_top_y, l.width + 2*l.bleed, spec['top_bar'] + l.bleed, 1, 0)

    # Use Shared Identity Block
    # Theme Light (White BG) but we want clean text.
    # Actually Minimal has Dark Text on White.
    draw_identity_block(
        c, 
        x=0, y=band_y, w=l.width, h=header_h, 
        asset=asset, storage=get_storage(), 
        theme='light'
    )

    # --- QR Code ---
    footer_h = spec['footer_band']
    qr_zone_top = band_y
    qr_zone_bot = footer_h
    
    qr_zone_h = qr_zone_top - qr_zone_bot
    center_y = qr_zone_bot + (qr_zone_h / 2)
    center_x = l.width / 2

    qr_size = spec['qr_size']
    pad = spec['qr_padding']
    
    # Card
    card_size = qr_size + (2 * pad)
    card_x = center_x - (card_size / 2)
    card_y = center_y - (card_size / 2)
    radius = to_pt(0.25)
    
    c.setStrokeColorRGB(*hex_to_rgb(COLORS['rules']))
    c.setLineWidth(2)
    c.setFillColorRGB(1, 1, 1)
    c.roundRect(card_x, card_y, card_size, card_size, radius, fill=1, stroke=1)
    
    # QR Content
    code = _read(asset, 'code')
    qr_url = f"{PUBLIC_BASE_URL.rstrip('/')}/r/{code}" # USE PUBLIC URL
    draw_qr(c, qr_url, x=center_x - qr_size/2, y=center_y - qr_size/2, size=qr_size, user_id=user_id)
 
    # --- Footer ---
    cta_text = CTA_MAP.get(_read(asset, 'cta_key'), 'SCAN FOR DETAILS')
    display_url = f"{urllib.parse.urlparse(PUBLIC_BASE_URL).netloc}/r/{code}"

    _draw_safe_footer_stack(
        c, l, center_x, 
        cta_text, display_url, 
        spec['fonts']['cta'], spec['fonts']['url'], 
        l.width - (2*l.safe_margin), 
        COLORS['bg_navy'], COLORS['secondary_text'], 
        cta_lines=1
    )


def _draw_agent_brand(c, l, asset, user_id):
    """Agent Brand with Shared Identity Block."""
    spec = l.layout_spec
    
    # --- Top Band (Shared Block) ---
    band_h = spec['top_band']
    band_y = l.height - band_h
    
    # Draw Dark Theme Identity Block directly
    draw_identity_block(
        c, 
        x=-l.bleed, y=band_y, w=l.width+2*l.bleed, h=band_h+l.bleed, # Bleed cover
        asset=asset, storage=get_storage(), 
        theme='dark'
    )
    
    # --- QR Code ---
    qr_size = spec['qr_size']
    pad = spec['qr_padding']
    
    top_of_footer = spec['footer_band']
    bot_of_header = band_y
    qr_y_center = top_of_footer + ((bot_of_header - top_of_footer) / 2)
    
    center_x = l.width / 2
    
    card_size = qr_size + (2 * pad)
    radius = to_pt(0.25)
    
    c.setStrokeColorRGB(*hex_to_rgb(COLORS['rules']))
    c.setLineWidth(2)
    c.setFillColorRGB(1, 1, 1)
    c.roundRect((l.width - card_size)/2, qr_y_center - (card_size/2), card_size, card_size, radius, fill=1, stroke=1)

    code = _read(asset, 'code')
    qr_url = f"{PUBLIC_BASE_URL.rstrip('/')}/r/{code}"
    draw_qr(c, qr_url, x=(l.width - qr_size)/2, y=qr_y_center - (qr_size/2), size=qr_size, user_id=user_id)
    
    # --- Footer ---
    # Just Scan Label under QR in whitespace
    # And maybe duplicate URL small?
    
    display_url = f"{urllib.parse.urlparse(PUBLIC_BASE_URL).netloc}/r/{code}"
    label_y = qr_y_center - (card_size/2) - to_pt(0.5)
    c.setFillColorRGB(*hex_to_rgb(COLORS['bg_navy'])) # Higher Contrast
    draw_fitted_multiline(c, display_url, center_x, label_y, FONT_BODY, 24, 18, l.width*0.8, align='center')

    # Footer Band CTA
    cta_text = CTA_MAP.get(_read(asset, 'cta_key'), 'SCAN FOR DETAILS')
    fs = spec['fonts']['cta']
    
    # Draw Centered in Footer Band
    footer_cy = top_of_footer / 2
    
    # Simple centered CTA
    draw_fitted_multiline(c, cta_text, center_x, footer_cy + (fs[0]*0.35), FONT_MED, fs[0], fs[1], l.width*0.9, max_lines=1, color=COLORS['bg_navy'])


def _draw_photo_banner(c, l, asset, user_id):
    """Legacy Photo Banner - Updated to use Fonts/PublicURL but keep layout."""
    spec = l.layout_spec
    margin = l.safe_margin

    # Top Band Color
    color_id = _read(asset, 'banner_color_id')
    bar_color = BANNER_COLOR_PALETTE.get(color_id, BANNER_COLOR_PALETTE['navy'])
    
    band_h = spec['top_band']
    band_y = l.height - band_h
    c.setFillColorRGB(*hex_to_rgb(bar_color))
    c.rect(-l.bleed, band_y, l.width + 2*l.bleed, band_h + l.bleed, 1, 0)
    
    # Use Identity Block on top? 
    # The Photo Banner layout is stricter (Text Right, Photo Left).
    # Let's map it to Identity Block for consistency!
    # Theme dark usually.
    draw_identity_block(
        c, 
        x=-l.bleed, y=band_y, w=l.width+2*l.bleed, h=band_h+l.bleed,
        asset=asset, storage=get_storage(), 
        theme='dark'
    )

    # Content
    # Same QR logic
    qr_size = spec['qr_size']
    pad = spec['qr_padding']
    qr_y = (band_y + spec['footer_band']) / 2
    
    code = _read(asset, 'code')
    qr_url = f"{PUBLIC_BASE_URL.rstrip('/')}/r/{code}"
    draw_qr(c, qr_url, x=(l.width - qr_size)/2, y=qr_y - qr_size/2, size=qr_size, user_id=user_id)
    
    # Footer CTA
    cta_text = CTA_MAP.get(_read(asset, 'cta_key'), 'SCAN FOR DETAILS')
    draw_fitted_multiline(c, cta_text, l.width/2, spec['footer_band']/2 + 20, FONT_MED, 80, 60, l.width*0.9, color=COLORS['bg_navy'])
