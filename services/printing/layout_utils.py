"""
Layout Utilities for SmartSign PDFs.

Handles:
1. Font Registration (Inter Family, with Fallbacks).
2. Shared Identity Block Rendering (Headshot, Name, Details, Brokerage).
3. Text Fitting Utilities.
"""
import os
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader
from reportlab.lib.colors import HexColor

# 1. Font Registration
FONTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "static", "fonts")

# Safe Fallbacks (Helvetica used only as a last resort in non-prod)
FONT_BODY = "Helvetica"
FONT_MED = "Helvetica"
FONT_BOLD = "Helvetica-Bold"
FONT_SERIF = "Helvetica"     # Fallback
FONT_SCRIPT = "Helvetica"    # Fallback

_fonts_registered = False

def register_fonts():
    """
    Register Inter fonts from static/fonts/.
    Raises RuntimeError in production if required fonts are missing.
    """
    global FONT_BODY, FONT_MED, FONT_BOLD, FONT_SERIF, FONT_SCRIPT, _fonts_registered
    
    if _fonts_registered:
        return
        
    # Search for fonts recursively under static/fonts
    found_fonts = {}
    target_fonts = {
        "Inter-Regular.ttf": "Regular",
        "Inter-Medium.ttf": "Medium",
        "Inter-Bold.ttf": "Bold",
        "BodoniModa-VariableFont_opsz,wght.ttf": "Bodoni",
        "Allura-Regular.ttf": "Allura"
    }
    
    for root, dirs, files in os.walk(FONTS_DIR):
        for f in files:
            if f in target_fonts:
                found_fonts[f] = os.path.join(root, f)

    # Required for success: Regular and Bold
    has_required = "Inter-Regular.ttf" in found_fonts and "Inter-Bold.ttf" in found_fonts
    
    from config import IS_PRODUCTION
    if not has_required and IS_PRODUCTION:
        raise RuntimeError(f"CRITICAL: Required Inter fonts (Regular/Bold) missing from {FONTS_DIR}. SmartSigns cannot be generated.")

    try:
        if "Inter-Regular.ttf" in found_fonts:
            pdfmetrics.registerFont(TTFont('Inter-Regular', found_fonts["Inter-Regular.ttf"]))
            FONT_BODY = 'Inter-Regular'
            
        if "Inter-Medium.ttf" in found_fonts:
            pdfmetrics.registerFont(TTFont('Inter-Medium', found_fonts["Inter-Medium.ttf"]))
            FONT_MED = 'Inter-Medium'
            
        if "Inter-Bold.ttf" in found_fonts:
            pdfmetrics.registerFont(TTFont('Inter-Bold', found_fonts["Inter-Bold.ttf"]))
            FONT_BOLD = 'Inter-Bold'
            
        # New Premium Fonts (SmartSign V2)
        if "BodoniModa-VariableFont_opsz,wght.ttf" in found_fonts:
            pdfmetrics.registerFont(TTFont('BodoniModa', found_fonts["BodoniModa-VariableFont_opsz,wght.ttf"]))
            FONT_SERIF = 'BodoniModa'
            
        if "Allura-Regular.ttf" in found_fonts:
            pdfmetrics.registerFont(TTFont('Allura', found_fonts["Allura-Regular.ttf"]))
            FONT_SCRIPT = 'Allura'
            
        # Success if we got the essentials
        if FONT_BODY == 'Inter-Regular' and FONT_BOLD == 'Inter-Bold':
            _fonts_registered = True
            
    except Exception as e:
        if IS_PRODUCTION:
            raise RuntimeError(f"CRITICAL: Failed to register Inter fonts: {e}")
        import logging
        logging.getLogger(__name__).warning(f"[PDF Utils] Warning: Failed to register Inter fonts: {e}")

# 1.1 Phone Formatting
def format_phone(raw):
    """
    Formats phone numbers: (XXX) XXX-XXXX
    """
    if not raw: return ""
    import re
    digits = re.sub(r'\D', '', str(raw))
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    if len(digits) == 11 and digits.startswith('1'):
        return f"1 ({digits[1:4]}) {digits[4:7]}-{digits[7:]}"
    return str(raw).strip()

def fit_text_one_line(c, text, font_name, max_width, max_font, min_font):
    """
    Fit text into a single line by reducing font size.
    Returns: chosen_size
    """
    if not text: return min_font
    
    current_size = max_font
    while current_size >= min_font:
        c.setFont(font_name, current_size)
        if c.stringWidth(text, font_name, current_size) <= max_width:
            return current_size
        current_size -= 1
        
    return min_font

def draw_fitted_text_block(c, text_list, x, y_top, w, align='center', font_map=None, leading=1.2):
    """
    Draw a block of text lines, auto-fitting each to width if needed.
    text_list: list of dicts {'text': str, 'font': str, 'size': int, 'color': hex}
    """
    if not text_list: return 0
    
    cursor_y = y_top
    
    for item in text_list:
        txt = item.get('text')
        if not txt: continue
        
        font = item.get('font', FONT_BODY)
        size = item.get('size', 12)
        color = item.get('color', '#000000')
        min_s = item.get('min_size', size * 0.7)
        
        # Fit
        final_size = fit_text_one_line(c, txt, font, w, size, min_s)
        
        # Draw
        c.setFont(font, final_size)
        c.setFillColor(HexColor(color))
        
        # Baseline correction (approx cap height)
        draw_y = cursor_y - final_size
        
        if align == 'center':
            c.drawCentredString(x + w/2, draw_y, txt)
        elif align == 'right':
            c.drawRightString(x + w, draw_y, txt)
        else:
            c.drawString(x, draw_y, txt)
            
        cursor_y -= (final_size * leading)
        
    return y_top - cursor_y


# 3. Identity Block
def draw_identity_block(c, x, y, w, h, asset, storage, theme='dark', cta_text=None):
    """
    Draws the shared Realtor-Grade Identity Block.
    Layout: [Headshot/Initials] [Name/Phone/Email] ... [Brokerage]
    
    Args:
        c: Canvas
        x, y: Bottom-Left corner of header band (not safe area, actual band)
        w, h: Band width/height
        asset: Metadata source
    """
    # Colors
    is_dark = (theme == 'dark')
    text_primary = '#ffffff' if is_dark else '#0f172a'
    text_secondary = '#cbd5e1' if is_dark else '#475569'
    bg_color = '#0f172a' if is_dark else '#ffffff'
    
    # Render Band Background
    c.setFillColor(HexColor(bg_color))
    c.rect(x, y, w, h, fill=1, stroke=0)

    # Safe Margins
    # We'll assume x,y,w,h is the "Band Area". Safe content should be inside.
    margin = h * 0.15
    content_top = y + h - margin
    content_bottom = y + margin

    # Optional CTA row (top of band)
    info_top = content_top
    if cta_text:
        cta_txt = str(cta_text).strip()
        if cta_txt:
            available_h = max(0, content_top - content_bottom)
            # Guarantee usable space for identity content (headshot + text)
            min_info_h = max(available_h * 0.55, 42)
            cta_h = min(available_h * 0.24, max(0, available_h - min_info_h))
            if cta_h > 0:
                cta_u = cta_txt.upper()
                cta_max_w = max(0, w - (2 * margin))
                max_font = max(12, cta_h * 0.55)
                min_font = max(10, cta_h * 0.35)
                size = fit_text_one_line(c, cta_u, FONT_BOLD, cta_max_w, max_font, min_font)

                c.setFillColor(HexColor(text_primary))
                c.setFont(FONT_BOLD, size)
                cta_center_y = content_top - (cta_h / 2)
                c.drawCentredString(x + (w / 2), cta_center_y - (size * 0.35), cta_u)

                # Divider line between CTA and identity content
                divider_y = content_top - cta_h
                c.setStrokeColor(HexColor('#334155' if is_dark else '#e2e8f0'))
                c.setLineWidth(1)
                c.line(x + margin, divider_y, x + w - margin, divider_y)

                info_top = divider_y - (h * 0.06)

    # Identity content region (below CTA)
    safe_h = max(0, info_top - content_bottom)
    content_y_top = info_top
    # --- 1. Headshot (Left) ---
    head_size = safe_h
    head_x = x + margin
    head_y = y + margin
    
    head_key = asset.get('headshot_key') or asset.get('agent_headshot_key')
    has_head = False
    
    # Helper to read asset
    def _get(k): return asset.get(k) or ""

    if head_key and storage.exists(head_key):
        try:
            c.saveState()
            # Clip Circle
            p = c.beginPath()
            p.circle(head_x + head_size/2, head_y + head_size/2, head_size/2)
            c.clipPath(p, stroke=0)
            
            img_data = storage.get_file(head_key)
            img = ImageReader(img_data)
            c.drawImage(img, head_x, head_y, width=head_size, height=head_size)
            c.restoreState()
            has_head = True
            
            # Border
            c.setStrokeColor(HexColor('#ffffff' if is_dark else '#000000'))
            c.setLineWidth(1)
            c.circle(head_x + head_size/2, head_y + head_size/2, head_size/2, stroke=1, fill=0)
            
        except Exception: pass

    if not has_head:
        # Initials Fallback
        name = _get('brand_name') or _get('agent_name') or "?"
        initials = "".join([n[0] for n in name.split()[:2]]).upper()
        
        c.setFillColor(HexColor('#334155'))
        c.circle(head_x + head_size/2, head_y + head_size/2, head_size/2, fill=1, stroke=0)
        
        c.setFillColor(HexColor('#ffffff'))
        c.setFont(FONT_BOLD, head_size * 0.4)
        c.drawCentredString(head_x + head_size/2, head_y + head_size/2 - (head_size*0.15), initials)

    # --- 2. Identity Details (Left of Center) ---
    info_x = head_x + head_size + (margin * 1.5)
    # Available width logic:
    # Reserve 30% for Brokerage on right
    # Use remaining center space
    
    info_w = w * 0.45
    
    name_txt = (_get('brand_name') or _get('agent_name') or "Agent Name").strip()
    phone_txt = _get('phone') or _get('agent_phone') or ""
    email_txt = _get('email') or _get('agent_email')
    
    # Render Stack
    lines = [
        {'text': name_txt, 'font': FONT_BOLD, 'size': head_size * 0.35, 'color': text_primary},
    ]
    if phone_txt:
        formatted_phone = format_phone(phone_txt)
        lines.append({'text': formatted_phone, 'font': FONT_BOLD, 'size': head_size * 0.22, 'color': text_primary})
    if email_txt:
        lines.append({'text': email_txt, 'font': FONT_MED, 'size': head_size * 0.18, 'color': text_secondary})
        
    draw_fitted_text_block(c, lines, info_x, content_y_top, info_w, align='left')
    
    # --- 3. Brokerage (Right) ---
    right_margin = x + w - margin
    brok_w = w * 0.30
    
    logo_key = asset.get('logo_key') or asset.get('agent_logo_key')
    drawn_logo = False
    
    if logo_key and storage.exists(logo_key):
        try:
             l_data = storage.get_file(logo_key)
             l_img = ImageReader(l_data)
             iw, ih = l_img.getSize()
             aspect = iw / ih
             
             draw_w = safe_h * aspect
             draw_h = safe_h
             
             if draw_w > brok_w:
                 draw_w = brok_w
                 draw_h = draw_w / aspect
                 
             # Right Align
             c.drawImage(l_img, right_margin - draw_w, head_y + (safe_h - draw_h)/2, width=draw_w, height=draw_h, mask='auto')
             drawn_logo = True
        except: pass
        
    if not drawn_logo:
        # Brokerage Text Fallback
        brok_name = asset.get('brokerage_name') or asset.get('brokerage')
        if brok_name:
             draw_fitted_text_block(
                 c, 
                 [{'text': str(brok_name).strip(), 'font': FONT_MED, 'size': head_size * 0.22, 'color': text_secondary}],
                 right_margin - brok_w, content_y_top - (safe_h * 0.3), brok_w, align='right'
             )
