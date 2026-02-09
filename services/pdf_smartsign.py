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
import services.printing.layout_utils as lu
import urllib.parse

# Preset CTA texts (Benefit Driven Check)
CTA_MAP = {
    'scan_for_details': 'SCAN FOR MORE INFO',
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
        },
        'smart_v2_vertical_banner': {
             'safe_margin_in': 0.5,
             'rail_width_percent': 0.22,
             'qr_percent': 0.35, 
             'headshot_percent': 0.28,
             'fonts': {
                 'status': (72, 54),
                 'cta': (48, 36),
                 'name': (72, 48),
                 'phone': (42, 32),
                 'license': (20, 16)
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
        },
        'smart_v2_vertical_banner': {
             'safe_margin_in': 0.75,
             'rail_width_percent': 0.22,
             'qr_percent': 0.35,
             'headshot_percent': 0.28,
             'fonts': {
                 'status': (100, 72),
                 'cta': (64, 48),
                 'name': (96, 72),
                 'phone': (54, 42),
                 'license': (24, 18)
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
        },
        'smart_v2_vertical_banner': {
             'safe_margin_in': 0.60,
             'rail_width_percent': 0.22,
             'qr_percent': 0.35,
             'headshot_percent': 0.28,
             'fonts': {
                 'status': (80, 60),
                 'cta': (54, 40),
                 'name': (84, 60),
                 'phone': (48, 36),
                 'license': (22, 16)
             }
        }
    },
    # --- New Premium Layouts Specs (Phase 3) ---
    '18x24': {
        # ... existing ...
        'smart_v2_modern_split': {
            'split': 0.5, 'padding': to_pt(0.75),
            'qr_percent': 0.30,
            'fonts': {'name':(48,36), 'cta':(60,48)}
        },
        'smart_v2_elegant_serif': {
            'margin': to_pt(1.0), 'border': 2,
            'qr_size': to_pt(4.0),
            'fonts': {'status':(96,72), 'cta':(24,18), 'name':(32,24)}
        },
        'smart_v2_bold_frame': {
            'border_in': 1.0, 
            'qr_percent': 0.50,
            'fonts': {'status':(110,80), 'cta':(48,36)}
        }
    },
    '24x36': {
        # ... existing ...
        'smart_v2_modern_split': {
            'split': 0.5, 'padding': to_pt(1.0),
            'qr_percent': 0.30,
            'fonts': {'name':(72,54), 'cta':(80,64)}
        },
        'smart_v2_elegant_serif': {
            'margin': to_pt(1.5), 'border': 3,
            'qr_size': to_pt(6.0),
            'fonts': {'status':(140,100), 'cta':(36,28), 'name':(48,36)}
        },
        'smart_v2_bold_frame': {
            'border_in': 1.5,
            'qr_percent': 0.50,
            'fonts': {'status':(150,110), 'cta':(72,54)}
        }
    },
    '36x24': {
         # ... existing ...
         'smart_v2_modern_split': {
            'split': 0.5, 'padding': to_pt(1.0),
            'qr_percent': 0.30,
            'fonts': {'name':(64,48), 'cta':(72,56)}
        },
        'smart_v2_elegant_serif': {
             'margin': to_pt(1.2), 'border': 3,
             'qr_size': to_pt(5.0),
             'fonts': {'status':(120,90), 'cta':(30,24), 'name':(40,30)}
        },
        'smart_v2_bold_frame': {
             'border_in': 1.25,
             'qr_percent': 0.45,
             'fonts': {'status':(130,100), 'cta':(60,48)}
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
        c, url_text, center_x, safe_bottom_y + url_fs, lu.FONT_BODY, 
        url_font[0], url_font[1], max_w, max_lines=1, align='center', color=url_color
    )
    
    # 2. CTA
    padding = to_pt(0.25)
    cta_bottom_limit = safe_bottom_y + url_fs + padding + url_fs # Push up more
    
    # Reuse multiline fitting
    res = calculate_fitted_multiline(
        c, cta_text, lu.FONT_BOLD, cta_font[0], cta_font[1], max_w, max_lines=cta_lines
    )
    
    y_start = cta_bottom_limit + ( (len(res['lines']) - 1) * res['line_height'] )
    
    c.setFillColorRGB(*hex_to_rgb(text_color))
    c.setFont(lu.FONT_BOLD, res['size'])
    
    for i, line in enumerate(res['lines']):
        draw_y = y_start - (i * res['line_height'])
        c.drawCentredString(center_x, draw_y, line)
        
    return 


def generate_smartsign_pdf(asset, order_id=None, user_id=None, override_base_url=None):
    # 0. Register Fonts
    lu.register_fonts()

    # 1. Extract Config
    size_key = _read(asset, 'print_size') or _read(asset, 'size') or DEFAULT_SIGN_SIZE
    if size_key not in SIGN_SIZES: size_key = DEFAULT_SIGN_SIZE

    layout_id = _read(asset, 'layout_id', 'smart_v1_minimal')
    valid_layouts = [
        'smart_v1_minimal', 'smart_v1_agent_brand', 'smart_v1_photo_banner', 
        'smart_v2_vertical_banner', 'smart_v2_modern_round',
        'smart_v2_modern_split', 'smart_v2_elegant_serif', 'smart_v2_bold_frame'
    ]
    if layout_id not in valid_layouts:
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
    active_base_url = override_base_url or PUBLIC_BASE_URL
    if layout_id == 'smart_v1_photo_banner':
        _draw_photo_banner(c, layout, asset, user_id, active_base_url)
    elif layout_id == 'smart_v1_agent_brand':
        _draw_agent_brand(c, layout, asset, user_id, active_base_url)
    elif layout_id == 'smart_v2_vertical_banner':
        _draw_smart_v2_vertical_banner(c, layout, asset, user_id, active_base_url)
    elif layout_id == 'smart_v2_modern_round':
        _draw_modern_round(c, layout, asset, user_id, active_base_url)
    elif layout_id == 'smart_v2_modern_split':
        _draw_modern_split(c, layout, asset, user_id, active_base_url)
    elif layout_id == 'smart_v2_elegant_serif':
        _draw_elegant_serif(c, layout, asset, user_id, active_base_url)
    elif layout_id == 'smart_v2_bold_frame':
        _draw_bold_frame(c, layout, asset, user_id, active_base_url)
    else:
        _draw_modern_minimal(c, layout, asset, user_id, active_base_url)
        
    c.showPage()
    c.save()
    buffer.seek(0)
    
    # Storage
    from utils.filenames import make_sign_asset_basename
    basename = make_sign_asset_basename(order_id if order_id else 0, size_key)
    folder = f"pdfs/order_{order_id}" if order_id else "pdfs/tmp_smartsign"
    
    # Append layout_id to filename to distinguish variants
    # Clean layout_id for filename safety just in case
    safe_layout = layout_id.replace("smart_", "")
    key = f"{folder}/{basename}_smart_{safe_layout}.pdf"
    
    storage = get_storage()
    storage.put_file(buffer, key, content_type="application/pdf")
    
    return key


def _draw_modern_round(c, l, asset, user_id, base_url):
    """
    Modern Round: White Circular Badge with inset QR + clean typography.
    """
    # 1. Background (White)
    c.setFillColorRGB(1, 1, 1)
    c.rect(-l.bleed, -l.bleed, l.width + 2*l.bleed, l.height + 2*l.bleed, fill=1, stroke=0)
    
    center_x = l.width / 2
    
    # 2. Giant Circular Badge
    # Top centered roughly in upper 60%
    badge_dia = l.width * 0.66
    badge_y_center = l.height * 0.55
    
    # White with Black Stroke
    c.setFillColorRGB(1, 1, 1)
    c.setStrokeColorRGB(0, 0, 0)
    c.setLineWidth(5)
    c.circle(center_x, badge_y_center, badge_dia/2, stroke=1, fill=1)
    
    # 3. Safe QR Size (Inscribed Square)
    # D * 0.707. Using 0.65 for explicit margin.
    qr_size = badge_dia * 0.65
    
    code = _read(asset, 'code')
    qr_url = f"{base_url.rstrip('/')}/r/{code}"
    draw_qr(c, qr_url, x=center_x - qr_size/2, y=badge_y_center - qr_size/2, size=qr_size, user_id=user_id, ecc_level="H")
    
    # 4. Center Logo/Headshot (Overlay)
    head_d = badge_dia * 0.25
    head_key = _read(asset, 'headshot_key') or _read(asset, 'agent_headshot_key')
    storage = get_storage()
    
    # Draw white circle background for logo to clear noise
    c.setFillColorRGB(1, 1, 1)
    c.setStrokeColorRGB(1, 1, 1) 
    c.circle(center_x, badge_y_center, head_d/2 + to_pt(0.1), fill=1, stroke=1) # slightly larger
    
    if head_key and storage.exists(head_key):
        try:
            c.saveState()
            p = c.beginPath()
            p.circle(center_x, badge_y_center, head_d/2)
            c.clipPath(p, stroke=0)
            
            img_data = storage.get_file(head_key)
            img = ImageReader(img_data)
            c.drawImage(img, center_x - head_d/2, badge_y_center - head_d/2, width=head_d, height=head_d, mask='auto', preserveAspectRatio=True)
            c.restoreState()
        except: pass
        
    # 5. Header Text (Top)
    # "SCAN ME" or CTA
    cta_text = CTA_MAP.get(_read(asset, 'cta_key'), 'SCAN ME')
    c.setFillColorRGB(0, 0, 0)
    c.setFont(lu.FONT_BOLD, 80)
    c.drawCentredString(center_x, l.height - to_pt(3.0), cta_text)
    
    # 6. Bottom Branding
    # Agent Name / Powered By
    c.setFont(lu.FONT_MED, 36)
    c.drawCentredString(center_x, to_pt(2.5), "Powered by InSite")


def _draw_modern_split(c, l, asset, user_id, base_url):
    """
    Modern Split: 50/50 Editorial Layout.
    Left: Full Bleed Photo (Headshot or Property).
    Right: Clean Typography & QR.
    """
    # 1. Background (White Right)
    c.setFillColorRGB(1, 1, 1)
    c.rect(0, 0, l.width, l.height, fill=1, stroke=0)
    
    # 2. Left Photo Panel
    # Determine split info
    # For now hardcoded 50% split
    split_x = l.width * 0.5
    
    # Draw dark placeholder on left
    c.setFillColorRGB(0.95, 0.95, 0.95) # Light gray placeholder
    c.rect(-l.bleed, -l.bleed, split_x + l.bleed, l.height + 2*l.bleed, fill=1, stroke=0)
    
    # Try logic: Use property photo if available, else agent headshot
    # Actually for "SmartSign" usually it's Agent Brand focused.
    head_key = _read(asset, 'headshot_key') or _read(asset, 'agent_headshot_key')
    storage = get_storage()
    
    if head_key and storage.exists(head_key):
        try:
            c.saveState()
            p = c.beginPath()
            # Rect clip for left side
            p.rect(-l.bleed, -l.bleed, split_x + l.bleed, l.height + 2*l.bleed)
            c.clipPath(p, stroke=0)
            
            img_data = storage.get_file(head_key)
            img = ImageReader(img_data)
            
            # center crop logic simplified: draw image covering rect
            # We use drawImage with preserveAspectRatio=True usually, but here we want FILL.
            # ReportLab doesn't have "object-fit: cover". 
            # We draw it large and let clip handle it.
            iw, ih = img.getSize()
            aspect = iw / ih
            target_w = split_x + l.bleed
            target_h = l.height + 2*l.bleed
            target_aspect = target_w / target_h
            
            if aspect > target_aspect:
                # Image is wider -> Fit Height
                draw_h = target_h
                draw_w = draw_h * aspect
                offset_x = -l.bleed - ((draw_w - target_w) / 2)
                offset_y = -l.bleed
            else:
                # Image is taller -> Fit Width
                draw_w = target_w
                draw_h = draw_w / aspect
                offset_x = -l.bleed
                offset_y = -l.bleed - ((draw_h - target_h) / 2)
                
            c.drawImage(img, offset_x, offset_y, width=draw_w, height=draw_h)
            c.restoreState()
        except Exception as e:
            # Fallback text
            c.setFillColorRGB(0.5, 0.5, 0.5)
            c.drawCentredString(split_x/2, l.height/2, "PHOTO")

    # 3. Right Side Content
    # Center X of right panel
    center_rx = split_x + (l.width - split_x)/2
    
    spec = SPECS.get(l.size_key, SPECS['18x24']).get('smart_v2_modern_split', {})
    if not spec: spec = SPECS['18x24']['smart_v2_modern_split'] # fallback
    
    # QR Code
    qr_w = l.width * spec.get('qr_percent', 0.35)
    qr_y = l.height * 0.50
    
    code = _read(asset, 'code')
    qr_url = f"{base_url.rstrip('/')}/r/{code}"
    draw_qr(c, qr_url, x=center_rx - qr_w/2, y=qr_y - qr_w/2, size=qr_w, user_id=user_id)
    
    # Text Above: Agent Name
    name_text = _read(asset, 'agent_name') or "Agent Name"
    font_name = spec['fonts']['name']
    name_y = qr_y + (qr_w/2) + to_pt(1.0)
    
    c.setFillColorRGB(*hex_to_rgb(COLORS['base_text']))
    fit_name = lu.fit_text_one_line(c, name_text, lu.FONT_BODY, (l.width - split_x) * 0.8, font_name[0], font_name[1])
    c.setFont(lu.FONT_BODY, fit_name)
    c.drawCentredString(center_rx, name_y, name_text)
    
    # Text Below: CTA
    cta_text = CTA_MAP.get(_read(asset, 'cta_key'), 'SCAN TO CONNECT')
    font_cta = spec['fonts']['cta']
    cta_y = qr_y - (qr_w/2) - to_pt(0.8) - font_cta[0]
    
    c.setFillColorRGB(*hex_to_rgb(COLORS['bg_navy']))
    fit_cta = lu.fit_text_one_line(c, cta_text, lu.FONT_BOLD, (l.width - split_x) * 0.85, font_cta[0], font_cta[1])
    c.setFont(lu.FONT_BOLD, fit_cta)
    c.drawCentredString(center_rx, cta_y, cta_text)


def _draw_elegant_serif(c, l, asset, user_id, base_url):
    """
    Elegant Serif: Minimalist, Serif Typography, Gold Accents.
    """
    spec = SPECS.get(l.size_key, SPECS['18x24']).get('smart_v2_elegant_serif', {})
    
    # 1. Background (Pure White)
    c.setFillColorRGB(1, 1, 1)
    c.rect(-l.bleed, -l.bleed, l.width + 2*l.bleed, l.height + 2*l.bleed, fill=1, stroke=0)
    
    center_x = l.width / 2
    
    # 2. Main Status Text (Serif)
    # e.g. "For Sale", "Coming Soon", "Just Listed"
    status_text = (_read(asset, 'status_text') or "For Sale").upper()
    font_status_spec = spec['fonts']['status']
    
    # Position: Upper 40%
    status_y = l.height * 0.70
    
    c.setFillColorRGB(*hex_to_rgb(COLORS['base_text']))
    fit_status = lu.fit_text_one_line(c, status_text, lu.FONT_SERIF, l.width * 0.8, font_status_spec[0], font_status_spec[1])
    c.setFont(lu.FONT_SERIF, fit_status)
    c.drawCentredString(center_x, status_y, status_text)
    
    # 3. QR Code with Gold Border
    # User Request: Double the size
    original_qr = spec.get('qr_size', to_pt(5.0))
    qr_size = original_qr * 2.0
    
    # Re-center QR vertically since it's bigger now
    # Center of layout roughly
    qr_y = l.height * 0.45
    
    # Box Border
    pad = to_pt(0.2)
    box_size = qr_size + 2*pad
    
    c.setStrokeColor(HexColor('#C5A065')) # Gold/Bronze
    c.setLineWidth(spec.get('border', 2))
    c.setFillColorRGB(1, 1, 1)
    
    c.rect(center_x - box_size/2, qr_y - box_size/2, box_size, box_size, fill=1, stroke=1)
    
    code = _read(asset, 'code')
    qr_url = f"{base_url.rstrip('/')}/r/{code}"
    draw_qr(c, qr_url, x=center_x - qr_size/2, y=qr_y - qr_size/2, size=qr_size, user_id=user_id)
    
    # 4. Footer Info (Minimal)
    # Headshot (Centered Above Name)
    head_key = _read(asset, 'headshot_key') or _read(asset, 'agent_headshot_key')
    storage = get_storage()
    
    name_y = to_pt(3.0)
    
    if head_key and storage.exists(head_key):
        # Draw Headshot in gap between CTA and Name
        # Start at name_y and go up
        head_dia = to_pt(2.0)
        head_y = name_y + to_pt(1.5) 
        
        try:
            c.saveState()
            p = c.beginPath()
            p.circle(center_x, head_y, head_dia/2)
            c.clipPath(p, stroke=0)
            
            img_data = storage.get_file(head_key)
            img = ImageReader(img_data)
            c.drawImage(img, center_x - head_dia/2, head_y - head_dia/2, width=head_dia, height=head_dia, mask='auto', preserveAspectRatio=True)
            c.restoreState()
            
            # Gold ring border
            c.setStrokeColor(HexColor('#C5A065'))
            c.setLineWidth(1)
            c.circle(center_x, head_y, head_dia/2, stroke=1, fill=0)
        except Exception as e:
            pass

    # Agent Name
    name_text = _read(asset, 'agent_name') or "Agent Name"
    font_name = spec['fonts']['name']
    
    c.setFillColorRGB(*hex_to_rgb(COLORS['secondary_text']))
    c.setFont(lu.FONT_BODY, font_name[0]) # Fixed size small
    c.drawCentredString(center_x, name_y, name_text)
    
    # Contact Info (Phone / Email)
    phone_text = _read(asset, 'phone') or _read(asset, 'agent_phone')
    email_text = _read(asset, 'email') or _read(asset, 'agent_email')
    
    contact_y = name_y - font_name[0] - to_pt(0.2)
    contact_font_size = font_name[0] * 0.6
    c.setFont(lu.FONT_BODY, contact_font_size)
    c.setFillColorRGB(*hex_to_rgb(COLORS['secondary_text']))
    
    contact_lines = []
    if phone_text: contact_lines.append(phone_text)
    if email_text: contact_lines.append(email_text)
    
    if contact_lines:
        contact_str = " | ".join(contact_lines)
        c.drawCentredString(center_x, contact_y, contact_str)
    
    # CTA tiny below QR
    cta_key = _read(asset, 'cta_key')
    cta_text = CTA_MAP.get(cta_key, 'SCAN FOR DETAILS')
    
    font_cta = spec['fonts']['cta']
    c.setFont(lu.FONT_SERIF, font_cta[0])
    
    # Push further down from box
    cta_padding = to_pt(0.8) 
    cta_y = qr_y - (box_size/2) - cta_padding
    
    c.drawCentredString(center_x, cta_y, cta_text)


def _draw_bold_frame(c, l, asset, user_id, base_url):
    """
    Bold Frame: Thick colored border, high impact.
    """
    spec = SPECS.get(l.size_key, SPECS['18x24']).get('smart_v2_bold_frame', {})
    
    # 1. Background (White)
    c.setFillColorRGB(1, 1, 1)
    c.rect(-l.bleed, -l.bleed, l.width + 2*l.bleed, l.height + 2*l.bleed, fill=1, stroke=0)
    
    # 2. Thick Border (Inset)
    border_in = spec.get('border_in', 1.0) * inch
    border_rect_w = l.width - (2*border_in)
    border_rect_h = l.height - (2*border_in)
    
    # Draw huge stroke? Or rect?
    # Let's draw a rect stroke.
    color_id = _read(asset, 'banner_color_id')
    bar_color = BANNER_COLOR_PALETTE.get(color_id, BANNER_COLOR_PALETTE['navy'])
    
    # We want the border to BE the frame. 
    # Logic: Draw outer rect filled with color, inner rect white.
    c.setFillColorRGB(*hex_to_rgb(bar_color))
    c.rect(0, 0, l.width, l.height, fill=1, stroke=0) # Base fill color
    
    # Inner White
    c.setFillColorRGB(1, 1, 1)
    c.rect(border_in, border_in, border_rect_w, border_rect_h, fill=1, stroke=0)
    
    # 3. Content Area
    center_x = l.width / 2
    center_y = l.height / 2
    
    # QR Code (Huge)
    qr_target = l.width * spec.get('qr_percent', 0.5)
    # Ensure it fits inside border
    max_qr = min(qr_target, border_rect_w * 0.8)
    
    code = _read(asset, 'code')
    qr_url = f"{base_url.rstrip('/')}/r/{code}"
    draw_qr(c, qr_url, x=center_x - max_qr/2, y=center_y - max_qr/2, size=max_qr, user_id=user_id)
    
    # 4. Bold Text Top/Bottom
    # Status Top
    status_text = (_read(asset, 'status_text') or "FOR SALE").upper()
    font_status_spec = spec['fonts']['status']
    
    status_y = (l.height - border_in) - (border_rect_h * 0.15) # Top inside white area
    
    c.setFillColorRGB(*hex_to_rgb(COLORS['base_text']))
    fit_status = lu.fit_text_one_line(c, status_text, lu.FONT_BOLD, border_rect_w * 0.9, font_status_spec[0], font_status_spec[1])
    c.setFont(lu.FONT_BOLD, fit_status)
    c.drawCentredString(center_x, status_y, status_text)
    
    # CTA Bottom
    cta_text = CTA_MAP.get(_read(asset, 'cta_key'), 'SCAN FOR INFO')
    font_cta = spec['fonts']['cta']
    
    cta_y = border_in + (border_rect_h * 0.15)
    fit_cta = lu.fit_text_one_line(c, cta_text, lu.FONT_BOLD, border_rect_w * 0.8, font_cta[0], font_cta[1])
    c.setFont(lu.FONT_BOLD, fit_cta)
    c.drawCentredString(center_x, cta_y, cta_text)


def _draw_modern_minimal(c, l, asset, user_id, base_url):
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
    lu.draw_identity_block(
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
    qr_url = f"{base_url.rstrip('/')}/r/{code}" # USE PUBLIC URL
    draw_qr(c, qr_url, x=center_x - qr_size/2, y=center_y - qr_size/2, size=qr_size, user_id=user_id)
 
    # --- Footer ---
    cta_text = CTA_MAP.get(_read(asset, 'cta_key'), 'SCAN FOR DETAILS')
    display_url = f"{urllib.parse.urlparse(base_url).netloc}/r/{code}"

    _draw_safe_footer_stack(
        c, l, center_x, 
        cta_text, display_url, 
        spec['fonts']['cta'], spec['fonts']['url'], 
        l.width - (2*l.safe_margin), 
        COLORS['bg_navy'], COLORS['secondary_text'], 
        cta_lines=1
    )


def _draw_agent_brand(c, l, asset, user_id, base_url):
    """Agent Brand with Shared Identity Block."""
    spec = l.layout_spec
    
    # --- Top Band (Shared Block) ---
    band_h = spec['top_band']
    band_y = l.height - band_h
    
    # Draw Dark Theme Identity Block directly
    lu.draw_identity_block(
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
    qr_url = f"{base_url.rstrip('/')}/r/{code}"
    draw_qr(c, qr_url, x=(l.width - qr_size)/2, y=qr_y_center - (qr_size/2), size=qr_size, user_id=user_id)
    
    # --- Footer ---
    # Just Scan Label under QR in whitespace
    # And maybe duplicate URL small?
    
    display_url = f"{urllib.parse.urlparse(base_url).netloc}/r/{code}"
    label_y = qr_y_center - (card_size/2) - to_pt(0.5)
    c.setFillColorRGB(*hex_to_rgb(COLORS['bg_navy'])) # Higher Contrast
    draw_fitted_multiline(c, display_url, center_x, label_y, lu.FONT_BODY, 24, 18, l.width*0.8, align='center')

    # Footer Band CTA
    cta_text = CTA_MAP.get(_read(asset, 'cta_key'), 'SCAN FOR DETAILS')
    fs = spec['fonts']['cta1']
    
    # Draw Centered in Footer Band
    footer_cy = top_of_footer / 2
    
    # Simple centered CTA
    draw_fitted_multiline(c, cta_text, center_x, footer_cy + (fs[0]*0.35), lu.FONT_MED, fs[0], fs[1], l.width*0.9, max_lines=1, color=COLORS['bg_navy'])


def _draw_photo_banner(c, l, asset, user_id, base_url):
    """Legacy Photo Banner - Updated to use Fonts/PublicURL but keep layout."""
    spec = l.layout_spec
    # Fallback: if spec is None, get from SPECS directly with 18x24 default
    if spec is None:
        spec = SPECS.get(l.size_key, SPECS['18x24']).get('smart_v1_photo_banner')
        if spec is None:
            spec = SPECS['18x24']['smart_v1_photo_banner']
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
    lu.draw_identity_block(
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
    qr_url = f"{base_url.rstrip('/')}/r/{code}"
    draw_qr(c, qr_url, x=(l.width - qr_size)/2, y=qr_y - qr_size/2, size=qr_size, user_id=user_id)
    
    # Footer CTA
    cta_text = CTA_MAP.get(_read(asset, 'cta_key'), 'SCAN FOR DETAILS')
    draw_fitted_multiline(c, cta_text, l.width/2, spec['footer_band']/2 + 20, lu.FONT_MED, 80, 60, l.width*0.9, color=COLORS['bg_navy'])



def _draw_smart_v2_vertical_banner(c, l, asset, user_id, base_url):
    """
    Premium V2 Vertical Banner.
    Features:
    - Right Side Rail (Vertical Text)
    - Circular Headshot
    - Script Typography
    """
    spec = l.layout_spec
    safe_margin = to_pt(spec.get('safe_margin_in', 0.5))
    
    # --- 1. Background (Dark Theme Base) ---
    c.setFillColorRGB(*hex_to_rgb(COLORS['bg_navy'])) # Dark base
    c.rect(-l.bleed, -l.bleed, l.width + 2*l.bleed, l.height + 2*l.bleed, fill=1, stroke=0)
    
    # --- 2. Right Rail ---
    rail_w = l.width * spec['rail_width_percent']
    rail_x_start = l.width - rail_w
    
    # Render Divider Line? Or just rail area.
    # Let's put a subtle separator
    c.setStrokeColorRGB(1, 1, 1, 0.2)
    c.setLineWidth(1)
    c.line(rail_x_start, 0, rail_x_start, l.height)
    
    # Vertical Status Text
    status_text = (_read(asset, 'status_text') or "FOR SALE").upper()
    font_status = spec['fonts']['status']
    
    c.saveState()
    # Center of rail
    rail_center_x = rail_x_start + (rail_w / 2)
    rail_center_y = l.height / 2
    
    c.translate(rail_center_x, rail_center_y)
    c.rotate(-90)
    
    # Fit Text to Height (which is now width)
    avail_h = l.height - (safe_margin * 2)
    # Actually rail height is full height.
    
    c.setFillColorRGB(1, 1, 1) # White
    fit_size = lu.fit_text_one_line(c, status_text, lu.FONT_SERIF, avail_h, font_status[0], font_status[1])
    c.setFont(lu.FONT_SERIF, fit_size)
    c.drawCentredString(0, -fit_size * 0.35, status_text) # Optimize vertical center visually
    c.restoreState()
    
    # --- 3. Left Content Area ---
    content_w = rail_x_start
    content_center_x = content_w / 2
    
    # QR Code (Top)
    qr_size_target = l.width * spec['qr_percent']
    qr_y_center = l.height * 0.78 # Upper quadrant
    
    # Draw White Card for QR
    card_pad = to_pt(0.3)
    card_size = qr_size_target + (2 * card_pad)
    
    c.setFillColorRGB(1, 1, 1)
    c.setStrokeColorRGB(1, 1, 1)
    # Simple crisp box
    c.rect(content_center_x - card_size/2, qr_y_center - card_size/2, card_size, card_size, fill=1, stroke=0)
    
    code = _read(asset, 'code')
    qr_url = f"{base_url.rstrip('/')}/r/{code}"
    draw_qr(c, qr_url, x=content_center_x - qr_size_target/2, y=qr_y_center - qr_size_target/2, size=qr_size_target, user_id=user_id)
    
    # CTA (Under QR)
    # Script Font
    cta_text = CTA_MAP.get(_read(asset, 'cta_key'), 'Scan for Details') # Title Case for script?
    # Actually script looks better if we don't force UPPER.
    # Convert 'SCAN FOR DETAILS' -> Title Case if needed?
    # CTA_MAP values are UPPER. Let's title case them for the script font.
    cta_text = cta_text.title() 
    
    font_cta = spec['fonts']['cta']
    cta_y = qr_y_center - (card_size/2) - to_pt(0.4)
    
    c.setFillColorRGB(*hex_to_rgb(COLORS['cta_fallback'])) # Light Gray/Silver
    fit_cta = lu.fit_text_one_line(c, cta_text, lu.FONT_SCRIPT, content_w * 0.8, font_cta[0], font_cta[1])
    c.setFont(lu.FONT_SCRIPT, fit_cta)
    c.drawCentredString(content_center_x, cta_y, cta_text)
    
    # Agent Headshot (Circular)
    head_d = l.width * spec['headshot_percent']
    head_y_center = l.height * 0.45
    
    head_key = _read(asset, 'headshot_key') or _read(asset, 'agent_headshot_key')
    storage = get_storage()
    
    if head_key and storage.exists(head_key):
        try:
            c.saveState()
            # Clip
            p = c.beginPath()
            p.circle(content_center_x, head_y_center, head_d/2)
            c.clipPath(p, stroke=0)
            
            img_data = storage.get_file(head_key)
            img = ImageReader(img_data)
            c.drawImage(img, content_center_x - head_d/2, head_y_center - head_d/2, width=head_d, height=head_d)
            c.restoreState()
            
            # Gold/Bronze Ring
            c.setStrokeColor(HexColor('#C5A065')) # Bronze-ish
            c.setLineWidth(3)
            c.circle(content_center_x, head_y_center, head_d/2, stroke=1, fill=0)
        except:
            # Fallback circle
            c.setFillColor(HexColor('#333'))
            c.circle(content_center_x, head_y_center, head_d/2, fill=1, stroke=0)

    # Agent Name (Script)
    name_y = head_y_center - (head_d/2) - to_pt(0.5)
    # Prefer persisted agent_name, fallback to brand_name or placeholder
    name_text = _read(asset, 'agent_name') or _read(asset, 'brand_name') or "Agent Name"
    font_name = spec['fonts']['name']
    
    c.setFillColorRGB(1, 1, 1)
    fit_name = lu.fit_text_one_line(c, name_text, lu.FONT_SCRIPT, content_w * 0.9, font_name[0], font_name[1])
    c.setFont(lu.FONT_SCRIPT, fit_name)
    c.drawCentredString(content_center_x, name_y, name_text)
    
    # Phone (Sans Bold)
    phone_y = name_y - fit_name # Drop down
    # Prefer persisted agent_phone, fallback to phone
    phone_raw = _read(asset, 'agent_phone') or _read(asset, 'phone')
    phone_text = format_phone_local(phone_raw)
    font_phone = spec['fonts']['phone']
    
    c.setFillColorRGB(1, 1, 1)
    # Letter spacing?
    fit_phone = lu.fit_text_one_line(c, phone_text, lu.FONT_BOLD, content_w * 0.8, font_phone[0], font_phone[1])
    c.setFont(lu.FONT_BOLD, fit_phone)
    c.drawCentredString(content_center_x, phone_y, phone_text)
    
    # License Number (Optional)
    # Logic: 
    # If license_number empty -> Skip
    # If show_license_number explicitly False -> Skip
    # If None -> CA=True, else False
    
    lic_num = _read(asset, 'license_number')
    
    # Tri-State Logic
    option = _read(asset, 'show_license_option') # auto, show, hide
    legacy_bool = _read(asset, 'show_license_number') # Legacy boolean backup
    state = (_read(asset, 'state') or "").upper()
    
    should_show = False
    
    if option == 'show':
        should_show = True
    elif option == 'hide':
        should_show = False
    elif option == 'auto':
        # TODO: Move specific state logic to a config table
        if state == 'CA': should_show = True
    else:
        # Fallback for old data where option might be missing
        if legacy_bool is True:
            should_show = True
        elif legacy_bool is False:
            should_show = False
        else:
            # Default Auto
            if state == 'CA': should_show = True
            
    if should_show and lic_num:
        lic_label_ov = _read(asset, 'license_label_override')
        if lic_label_ov:
            label = lic_label_ov
        elif state == 'CA':
            label = "DRE #"
        else:
            label = "Lic #"
             
        full_lic = f"{label}{lic_num}"
        font_lic = spec['fonts']['license']
        lic_y = phone_y - fit_phone * 1.2
         
        c.setFillColorRGB(0.7, 0.7, 0.7) # Muted
        c.setFont(lu.FONT_BODY, font_lic[0]) # Small Sans
        c.drawCentredString(content_center_x, lic_y, full_lic)


    # Brokerage Logo (Bottom Center of Left Panel)
    logo_key = _read(asset, 'logo_key') or _read(asset, 'agent_logo_key')
    if logo_key and storage.exists(logo_key):
        try:
             # Draw Area
             footer_y = safe_margin
             max_h = to_pt(1.5) 
             max_w = content_w * 0.6
             
             l_data = storage.get_file(logo_key)
             l_img = ImageReader(l_data)
             iw, ih = l_img.getSize()
             aspect = iw / ih
             
             draw_w = max_h * aspect
             if draw_w > max_w:
                 draw_w = max_w
                 draw_h = draw_w / aspect
             else:
                 draw_h = max_h
                 
             c.drawImage(l_img, content_center_x - draw_w/2, footer_y, width=draw_w, height=draw_h, mask='auto', preserveAspectRatio=True)
        except: pass

def format_phone_local(raw):
    # Quick inline formatter if layout_utils isn't available
    if not raw: return ""
    import re
    digits = re.sub(r'\D', '', str(raw))
    if len(digits) == 10:
        return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"
    return str(raw)
