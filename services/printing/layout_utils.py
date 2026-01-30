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
INTER_DIR = os.path.join(FONTS_DIR, "Inter", "static")

# Safe Fallbacks
FONT_BODY = "Helvetica"
FONT_MED = "Helvetica"     # No native medium in standard 14 fonts
FONT_BOLD = "Helvetica-Bold"

_fonts_registered = False

def register_fonts():
    """
    Register Inter fonts from static/fonts/Inter/static.
    Updates global FONT constants if successful.
    """
    global FONT_BODY, FONT_MED, FONT_BOLD, _fonts_registered
    
    if _fonts_registered:
        return
        
    # Try Inter (Google Fonts static versions often have size suffix)
    # We'll try the 24pt versions as reference TTFs
    inter_reg = os.path.join(INTER_DIR, "Inter_24pt-Regular.ttf")
    inter_med = os.path.join(INTER_DIR, "Inter_24pt-Medium.ttf")
    inter_bold = os.path.join(INTER_DIR, "Inter_24pt-Bold.ttf")
    
    try:
        if os.path.exists(inter_reg):
            pdfmetrics.registerFont(TTFont('Inter-Regular', inter_reg))
            FONT_BODY = 'Inter-Regular'
            
        if os.path.exists(inter_med):
            pdfmetrics.registerFont(TTFont('Inter-Medium', inter_med))
            FONT_MED = 'Inter-Medium'
            
        if os.path.exists(inter_bold):
            pdfmetrics.registerFont(TTFont('Inter-Bold', inter_bold))
            FONT_BOLD = 'Inter-Bold'
            
        _fonts_registered = True
            
    except Exception as e:
        print(f"[PDF Utils] Error registering Inter fonts: {e}")


# 2. Text Fitting
def fit_text_one_line(c, text, font_name, max_width, max_font, min_font):
    """
    Fit text into a single line by reducing font size.
    Signature matches user requirement: (c, text, font_name, max_width, max_font, min_font)
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
def draw_identity_block(c, x, y, w, h, asset, storage, theme='dark'):
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
    # Assume global safety is handled by caller passing safe bounds? 
    # Or we verify safe margin inside the band.
    # We'll assume x,y,w,h is the "Band Area". Safe content should be inside.
    margin = h * 0.15
    safe_h = h - (2 * margin)
    content_y_top = y + h - margin
    
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
    
    name_txt = (_get('brand_name') or _get('agent_name') or "Agent Name").upper()
    phone_txt = _get('phone') or _get('agent_phone') or ""
    email_txt = _get('email') or _get('agent_email')
    
    # Render Stack
    lines = [
        {'text': name_txt, 'font': FONT_BOLD, 'size': head_size * 0.35, 'color': text_primary},
    ]
    if phone_txt:
        lines.append({'text': phone_txt, 'font': FONT_BOLD, 'size': head_size * 0.22, 'color': text_primary}) # High contrast for phone
    if email_txt:
        lines.append({'text': email_txt, 'font': FONT_MED, 'size': head_size * 0.18, 'color': text_secondary})
        
    draw_fitted_text_block(c, lines, info_x, content_y_top, info_w, align='left')
    
    # --- 3. Brokerage (Right) ---
    right_margin = x + w - margin
    brok_w = w * 0.30
    brok_x = right_margin - brok_w
    
    logo_key = _get('logo_key') or _get('agent_logo_key')
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
        brok_name = _get('brokerage_name')
        if brok_name:
             draw_fitted_text_block(
                 c, 
                 [{'text': brok_name, 'font': FONT_MED, 'size': head_size * 0.25, 'color': text_secondary}],
                 brok_x, content_y_top - (safe_h * 0.25), brok_w, align='right'
             )
