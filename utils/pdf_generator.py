"""
PDF Sign Generator with Size-Aware Layout.
Generates print-ready PDF signs that scale proportionally to any supported size.
Vector QR codes for print-grade sharpness using ReportLab's QrCodeWidget.
"""
import logging
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import inch
from reportlab.lib.utils import ImageReader
import os
import io
from constants import SIGN_SIZES, DEFAULT_SIGN_COLOR, DEFAULT_SIGN_SIZE
from utils.qr_vector import draw_vector_qr
from utils.storage import get_storage
from config import PUBLIC_BASE_URL
from utils.qr_urls import property_scan_url
import utils.pdf_text as pdf_text
from utils.yard_tokens import SAFE_MARGIN, BLEED, TYPE_SCALE_MODERN, SPACING, QR_MIN_SIZE, QR_QUIET_ZONE_FACTOR
from services.printing.layout_utils import (
    register_fonts, 
    draw_identity_block,
    FONT_BODY, FONT_BOLD, FONT_MED
)

class LayoutSpec:
    """
    Calculates dynamic font sizes and positions based on physical dimensions.
    """
    def __init__(self, width_in, height_in):
        self.width = width_in * inch
        self.height = height_in * inch
        self.bleed = 0.125 * inch
        self.margin = 0.5 * inch
        
        # Grid System for "House Style" (Vertical standard)
        self.header_y = self.height * 0.92  # Address
        self.features_y = self.height * 0.86
        self.qr_center_y = self.height * 0.60
        self.footer_height = self.height * 0.18 # Identity Block height
        
        # Font Scaling Factor (Base 18x24)
        scale = min(width_in, height_in) / 18.0
        
        self.address_font = 90 * scale
        self.features_font = 48 * scale
        self.price_font = 100 * scale
        self.cta_font = 36 * scale
        
        self.qr_size_base = self.width * 0.60
        
        # Compatibility fields for legacy layouts (if any survive)
        self.banner_height = self.footer_height
        self.price_y = self.height * 0.35

# =============================================================================
# QR Drawing Helper (Switchable Vector/Raster)
# =============================================================================
from utils.qr_vector import draw_vector_qr
from utils.qr_image import render_qr_png
from config import ENABLE_QR_LOGO
from reportlab.lib.utils import ImageReader
import io

logger = logging.getLogger(__name__)


# =============================================================================
# Text Fitting Utilities
# =============================================================================

def fit_text_single_line(c, text: str, max_width_pts: float, font_name: str, 
                          max_font_size: float, min_font_size: float = 8) -> float:
    """
    Find the largest font size that fits text within max_width.
    
    Args:
        c: ReportLab canvas (for stringWidth calculation)
        text: Text to measure
        max_width_pts: Maximum width in points
        font_name: Font to use for measurement
        max_font_size: Starting (maximum) font size
        min_font_size: Minimum acceptable font size
        
    Returns:
        The largest font size that fits, or min_font_size if text is too long.
    """
    from reportlab.pdfbase.pdfmetrics import stringWidth
    
    font_size = max_font_size
    while font_size >= min_font_size:
        width = stringWidth(text, font_name, font_size)
        if width <= max_width_pts:
            return font_size
        font_size -= 1
    return min_font_size


def wrap_text_to_width(text: str, max_width_pts: float, font_name: str, 
                        font_size: float, max_lines: int = 2) -> list[str]:
    """
    Wrap text to fit within a maximum width, returning a list of lines.
    
    Args:
        text: Text to wrap
        max_width_pts: Maximum width in points per line
        font_name: Font name for measurement
        font_size: Font size for measurement
        max_lines: Maximum number of lines to return
        
    Returns:
        List of text lines (capped at max_lines). 
        Last line is truncated with "..." if text overflows.
    """
    from reportlab.pdfbase.pdfmetrics import stringWidth
    
    words = text.split()
    if not words:
        return []
    
    lines = []
    current_line = []
    
    for word in words:
        test_line = ' '.join(current_line + [word])
        if stringWidth(test_line, font_name, font_size) <= max_width_pts:
            current_line.append(word)
        else:
            if current_line:
                lines.append(' '.join(current_line))
                if len(lines) >= max_lines:
                    # Truncate with ellipsis
                    last = lines[-1]
                    while stringWidth(last + '...', font_name, font_size) > max_width_pts and len(last) > 5:
                        last = last[:-1].rstrip()
                    lines[-1] = last + '...'
                    return lines
                current_line = [word]
            else:
                # Single word too long, just add it (will overflow)
                lines.append(word)
                if len(lines) >= max_lines:
                    return lines
                current_line = []
    
    if current_line and len(lines) < max_lines:
        lines.append(' '.join(current_line))
    
    return lines

def draw_qr(c, qr_value: str, x, y, size, *, user_id: int | None = None, **kwargs):
    """
    Draw a QR code at (x, y) with dimension `size` x `size`.
    
    Logic:
    - If ENABLE_QR_LOGO is True AND user_id provided AND user has logo enabled:
        - Generate Raster PNG (ECC H + Logo)
        - Draw Image
    - Else:
        - Draw standard Vector QR (ECC M/H via kwargs)
    """
    # 1. Try Logo Path
    if ENABLE_QR_LOGO and user_id:
        try:
            # Lazy import to avoid circular dep / early DB access
            from services.branding import get_user_qr_logo_bytes
            
            logo_bytes = get_user_qr_logo_bytes(user_id)
            if logo_bytes:
                # Calculate resolution
                # ReportLab size is in points (1/72 inch)
                size_in = float(size) / 72.0
                # Target 300 DPI, min 1024, max 2400
                target_px = max(1024, min(2400, int(size_in * 300)))
                
                png_data = render_qr_png(qr_value, size_px=target_px, logo_png=logo_bytes)
                
                # ReportLab drawImage
                img_reader = ImageReader(io.BytesIO(png_data))
                c.drawImage(img_reader, x, y, width=size, height=size, mask='auto')
                return
        except Exception as e:
            logger.error(f"Failed to draw logo QR for user {user_id}: {e}. Fallback to vector.")
            
    # 2. Vector Fallback (Standard)
    # Pass kwargs like quiet, ecc_level
    draw_vector_qr(c, qr_value, x, y, size, **kwargs)



def hex_to_rgb(hex_color: str) -> tuple:
    """Convert hex color to RGB tuple (0-1 range for reportlab)."""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) / 255 for i in (0, 2, 4))


def generate_pdf_sign(address, beds, baths, sqft, price, agent_name, brokerage, agent_email, agent_phone,
                      qr_key=None, agent_photo_key=None, 
                      sign_color=None, sign_size=None, order_id=None, qr_value=None,
                      # Legacy parameters for backward compatibility with tests
                      qr_path=None, agent_photo_path=None, return_path=False,
                      user_id=None, logo_key=None, output_key=None, layout_id="smart_v1_photo_banner"):
    """
    Generate a PDF sign with customizable color and size.
    Layout scales proportionally to the page dimensions.
    
    Args:
        address: Property street address
        beds: Number of bedrooms
        baths: Number of bathrooms
        sqft: Square footage string (e.g. "2,500 sqft")
        price: Formatted price string (e.g. "$550,000")
        agent_name: Agent's full name
        brokerage: Brokerage name
        agent_email: Agent's email
        agent_phone: Agent's phone number
        qr_key: Storage key for QR code image (Legacy/Unused if vector)
        agent_photo_key: Storage key for agent photo
        sign_color: Hex color code (e.g. "#1F6FEB")
        sign_size: Size key from SIGN_SIZES (e.g. "18x24")
        order_id: Optional ID for tracking/filenames
        qr_value: The value to generate the QR code from (URL)
        user_id: The ID of the user (for logo preferences)
        logo_key: Storage key for brokerage/agent logo
        output_key: Explicit storage key to write to (overrides order_id logic)
        layout_id: Layout style identifier
    """
    # Explicit legacy mode detection:
    # - order_id is None AND output_key is None (local tooling)
    # - returning path explicitly requested
    legacy_mode = (order_id is None and output_key is None) or return_path or (qr_path is not None) or (agent_photo_path is not None)
    
    # Default values
    if not sign_color:
        sign_color = DEFAULT_SIGN_COLOR
    if not sign_size:
        sign_size = DEFAULT_SIGN_SIZE
    
    # Get size configuration
    size_config = SIGN_SIZES.get(sign_size, SIGN_SIZES[DEFAULT_SIGN_SIZE])
    
    # Create layout spec
    layout = LayoutSpec(size_config['width_in'], size_config['height_in'])
    
    # Create canvas in memory
    pdf_buffer = io.BytesIO()
    
    # Create canvas with bleed
    c = canvas.Canvas(
        pdf_buffer, 
        pagesize=(layout.width + 2 * layout.bleed, layout.height + 2 * layout.bleed)
    )
    
    # Determine if landscape (width > height)
    is_landscape = size_config['width_in'] > size_config['height_in']
    
    # Draw 2 identical pages (front/back)
    for page_num in range(2):
        c.saveState()
        c.translate(layout.bleed, layout.bleed)
        
        if layout_id == 'listing_modern_round':
             _draw_modern_round_layout(
                c, layout, address, beds, baths, sqft, price,
                agent_name, brokerage, agent_email, agent_phone,
                qr_key, agent_photo_key, sign_color, qr_value=qr_value,
                agent_photo_path=agent_photo_path, user_id=user_id, logo_key=logo_key
            )

        elif is_landscape:
            # House Style Landscape
            _draw_landscape_split_layout(
                c, layout, address, beds, baths, sqft, price,
                agent_name, brokerage, agent_email, agent_phone,
                qr_key, agent_photo_key, sign_color, qr_value=qr_value,
                agent_photo_path=agent_photo_path, user_id=user_id, logo_key=logo_key
            )
        else:
            # House Style Standard (Vertical)
            _draw_standard_layout(
                c, layout, address, beds, baths, sqft, price,
                agent_name, brokerage, agent_email, agent_phone,
                qr_key, agent_photo_key, sign_color, qr_value=qr_value,
                agent_photo_path=agent_photo_path, user_id=user_id, logo_key=logo_key
            )
        
        c.restoreState()
        c.showPage()
    
    c.save()
    
    pdf_buffer.seek(0)
    
    # Branch: Legacy mode returns filesystem path
    if legacy_mode:
        import tempfile
        # Write to temp file
        tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        tmp_file.write(pdf_buffer.read())
        tmp_file.close()
        return tmp_file.name
    
    # Normal mode: Upload PDF to storage
    from utils.filenames import make_sign_asset_basename
    
    if output_key:
        pdf_key = output_key
    else:
        # Use order_id if available, otherwise 'tmp'
        folder = f"pdfs/order_{order_id}" if order_id else "pdfs/tmp"
        basename = make_sign_asset_basename(order_id if order_id else 0, sign_size)
        pdf_key = f"{folder}/{basename}.pdf"
    
    storage = get_storage()
    storage.put_file(pdf_buffer, pdf_key, content_type="application/pdf")
    
    return pdf_key


def _draw_standard_layout(c, layout, address, beds, baths, sqft, price,
                          agent_name, brokerage, agent_email, agent_phone,
                          qr_key, agent_photo_key, sign_color, qr_value=None,
                          agent_photo_path=None, user_id=None, logo_key=None):
    """
    Standard "House Style" Layout | Vertical (18x24)
    Clean, whitespace-driven design using Inter fonts.
    """
    
    # 1. Header: Address (Top Centered)
    c.setFont(FONT_BOLD, layout.address_font)
    c.setFillColorRGB(0, 0, 0)
    c.drawCentredString(layout.width / 2, layout.header_y, address.upper())
    
    # 2. Subheader: Features (Below Address)
    c.setFont(FONT_MED, layout.features_font)
    c.setFillColorRGB(0.4, 0.4, 0.4)
    features_line = f"{beds} BEDS  |  {baths} BATHS"
    if sqft:
        features_line += f"  |  {sqft} SQ FT"
    c.drawCentredString(layout.width / 2, layout.features_y, features_line)
    
    # 3. Price (Floating, High Visibility)
    if price:
        display_price = price if "$" in str(price) else f"${price}"
        c.setFont(FONT_BOLD, layout.price_font)
        c.setFillColorRGB(*hex_to_rgb(sign_color)) # Use accent color
        # Draw vertically between features and QR
        price_y = (layout.features_y + layout.qr_center_y + layout.qr_size_base/2) / 2
        c.drawCentredString(layout.width / 2, price_y, display_price)
    
    # 4. QR Code (Central Focal Point)
    try:
        # Determine URL
        if qr_value:
            qr_url = qr_value
        elif qr_key:
            filename = os.path.basename(qr_key)
            code_part = os.path.splitext(filename)[0]
            # Use canonical helper
            qr_url = property_scan_url(PUBLIC_BASE_URL, code_part)
        else:
            qr_url = "https://example.com"

        # Size: 60% of width
        qr_size = layout.qr_size_base * 1.08
        qr_x = (layout.width - qr_size) / 2
        qr_y = layout.qr_center_y - (qr_size / 2)
        
        # 4a. Draw QR (Vector H-ECC)
        draw_qr(c, qr_url, qr_x, qr_y, qr_size, ecc_level="H", user_id=user_id)
        
    except Exception as e:
        logger.error(f"QR Draw Error: {e}")

    # 5. Footer: Identity Block (Shared Component)
    # Spans full width at bottom
    
    # Construct asset dict for shared component
    asset = {
        'brand_name': agent_name,
        'brokerage_name': brokerage,
        'email': agent_email,
        'phone': agent_phone,
        'headshot_key': agent_photo_key, 
        'logo_key': logo_key,
        # Legacy compat
        'agent_headshot_path': agent_photo_path 
    }
    
    # Draw Footer Band
    # Standard: Dark Theme
    draw_identity_block(
        c, 
        0, 0,  # x, y (Bottom Left)
        layout.width, layout.footer_height, # w, h
        asset, 
        get_storage(), 
        theme='dark',
        cta_text="SCAN FOR PHOTOS & DETAILS"
    )


def _draw_landscape_split_layout(c, layout, address, beds, baths, sqft, price,
                                 agent_name, brokerage, agent_email, agent_phone,
                                 qr_key, agent_photo_key, sign_color, qr_value=None,
                                 agent_photo_path=None, user_id=None, logo_key=None):
    """
    Landscape "House Style" Layout | Horizontal (24x36)
    Split 40/60 Layout:
    Left (40%): Property Info + Agent Identity Block
    Right (60%): Massive QR Code
    """
    # Dimensions
    w = layout.width
    h = layout.height
    band_h = layout.footer_height  # bottom identity band
    
    # Split
    split_x = w * 0.45
    
    # Margins
    margin_x = w * 0.04
    margin_y = h * 0.08
    
    # =====================================================
    # RIGHT COLUMN: QR with VECTOR RENDERING
    # =====================================================
    try:
        # Determine URL
        if qr_value:
            qr_url = qr_value
        elif qr_key:
            filename = os.path.basename(qr_key)
            code_part = os.path.splitext(filename)[0]
            qr_url = property_scan_url(PUBLIC_BASE_URL, code_part)
        else:
            qr_url = "https://example.com"
            
        # Maximize QR in the right column with large margins
        right_w = w - split_x
        quiet = max(0.02 * h, 0.25 * inch)
        
        qr_max_w = right_w - (2 * margin_x)
        body_h = h - band_h
        qr_max_h = body_h - (2 * margin_y)
        qr_size = min(qr_max_w, qr_max_h)
        
        # Center QR in right column
        qr_x = split_x + (right_w - qr_size) / 2
        qr_y = band_h + ((body_h - qr_size) / 2) 
        
        # Draw vector QR
        draw_qr(c, qr_url, qr_x, qr_y, qr_size, ecc_level="H", user_id=user_id)
        
    except Exception as e:
        logger.error(f"[PDF] Split Layout Vector QR Error: {e}")

    # =====================================================
    # LEFT COLUMN: INFO
    # =====================================================
    left_center = split_x / 2
    cursor_y = h - margin_y
    
    # 1. Address
    c.setFont(FONT_BOLD, layout.address_font * 0.8)
    c.setFillColorRGB(0, 0, 0)
    # Wrap address if needed? logic for now: draw centered in left col
    c.drawCentredString(left_center, cursor_y, address.upper())
    
    cursor_y -= (layout.address_font * 1.5)
    
    # 2. Features
    c.setFont(FONT_MED, layout.features_font * 0.9)
    c.setFillColorRGB(0.4, 0.4, 0.4)
    features_line = f"{beds} BEDS  |  {baths} BATHS"
    if sqft:
        features_line += f"  |  {sqft} SQ FT"
    c.drawCentredString(left_center, cursor_y, features_line)
    
    cursor_y -= (layout.features_font * 2.0)
    
    # 3. Price
    if price:
        display_price = price if "$" in str(price) else f"${price}"
        c.setFont(FONT_BOLD, layout.price_font * 0.9)
        c.setFillColorRGB(*hex_to_rgb(sign_color))
        c.drawCentredString(left_center, cursor_y, display_price)

    # 4. Identity Block (Bottom Left)
    # Construct asset
    asset = {
        'brand_name': agent_name,
        'brokerage_name': brokerage,
        'email': agent_email,
        'phone': agent_phone,
        'headshot_key': agent_photo_key,
        'logo_key': logo_key,
        'agent_headshot_path': agent_photo_path
    }
    
    draw_identity_block(
        c,
        0, 0,
        w, band_h,
        asset,
        get_storage(),
        theme='dark',
        cta_text="SCAN FOR PHOTOS & DETAILS"
    )
    # Divider Line
    c.setStrokeColorRGB(0.9, 0.9, 0.9)
    c.setLineWidth(2)
    c.line(split_x, band_h + margin_y, split_x, h - margin_y)



def _draw_centered_agent_info(c, layout, agent_main, agent_sub, logo_key=None):
    """Helper to draw centered agent info when no photo."""
    text_center_y = layout.banner_height / 2
    c.setFont("Helvetica-Bold", layout.agent_name_font)
    c.drawCentredString(layout.width / 2, text_center_y + (0.08 * layout.banner_height), agent_main)
    c.setFont("Helvetica", layout.agent_sub_font)
    c.drawCentredString(layout.width / 2, text_center_y - (0.12 * layout.banner_height), agent_sub)


def _draw_minimal_layout(c, layout, address, beds, baths, sqft, price,
                        agent_name, brokerage, agent_email, agent_phone,
                        qr_key, agent_photo_key, sign_color, qr_value=None,
                        agent_photo_path=None, user_id=None, logo_key=None):
    """
    Minimalist Layout: White background, Large QR, minimal styling.
    Top: QR Code (large)
    Middle: Address & Price
    Bottom: Agent Info
    """
    COLOR_TEXT = (0, 0, 0)
    COLOR_SUBTEXT = (0.5, 0.5, 0.5)
    
    # 1. Background (White)
    c.setFillColorRGB(1, 1, 1)
    c.rect(-layout.bleed, -layout.bleed, 
           layout.width + 2 * layout.bleed, 
           layout.height + 2 * layout.bleed, 
           fill=1, stroke=0)
           
    # 2. QR Code (Upper Center, Large)
    # Adjusted to prevent overlap with text
    qr_center_y = layout.height * 0.68
    qr_max_w = layout.width * 0.7
    qr_max_h = layout.height * 0.45
    qr_size = min(qr_max_w, qr_max_h)
    
    qr_x = (layout.width - qr_size) / 2
    qr_y = qr_center_y - (qr_size / 2)
    
    # Determine URL
    if qr_value:
        qr_url = qr_value
    elif qr_key:
        filename = os.path.basename(qr_key)
        code_part = os.path.splitext(filename)[0]
        qr_url = property_scan_url(PUBLIC_BASE_URL, code_part)
    else:
        qr_url = "https://example.com"

    try:
        draw_qr(c, qr_url, qr_x, qr_y, qr_size, ecc_level="H", user_id=user_id)
        
        # Scan me text
        c.setFont("Helvetica-Bold", layout.features_font * 0.8)
        c.setFillColorRGB(*COLOR_TEXT)
        c.drawCentredString(layout.width/2, qr_y - (layout.features_font * 1.5), "SCAN FOR PHOTOS")
        
    except Exception as e:
        print(f"[PDF] Minimal QR Error: {e}")

    # 3. Property Info (Middle-Lower)
    cursor_y = layout.height * 0.28  # Lowered from 0.35 to fix overlap
    
    # Address
    c.setFont("Helvetica-Bold", layout.address_font)
    c.setFillColorRGB(*COLOR_TEXT)
    c.drawCentredString(layout.width/2, cursor_y, address.upper())
    
    cursor_y -= (layout.address_font * 1.5)
    
    # Price
    if price:
        c.setFont("Helvetica-Bold", layout.price_font)
        c.setFillColorRGB(*hex_to_rgb(sign_color)) # Use accent color
        c.drawCentredString(layout.width/2, cursor_y, price)
        cursor_y -= (layout.price_font * 1.4)
        
    # Features
    c.setFont("Helvetica", layout.features_font)
    c.setFillColorRGB(*COLOR_SUBTEXT)
    line = f"{beds} BEDS | {baths} BATHS"
    if sqft: line += f" | {sqft} SQ FT"
    c.drawCentredString(layout.width/2, cursor_y, line)
    
    # 4. Agent Info (Bottom Footer, minimal)
    # Draw simple line separator
    line_y = layout.height * 0.12
    c.setStrokeColorRGB(0.9, 0.9, 0.9)
    c.setLineWidth(2)
    c.line(layout.margin, line_y, layout.width - layout.margin, line_y)
    
    # Agent Name & Phone
    c.setFont("Helvetica-Bold", layout.agent_name_font * 0.8)
    c.setFillColorRGB(*COLOR_TEXT)
    footer_text = f"{agent_name.upper()}  |  {brokerage.upper()}  |  {agent_phone}"
    c.drawCentredString(layout.width/2, line_y - (layout.agent_name_font * 1.5), footer_text)


def _draw_brand_layout(c, layout, address, beds, baths, sqft, price,
                        agent_name, brokerage, agent_email, agent_phone,
                        qr_key, agent_photo_key, sign_color, qr_value=None,
                        agent_photo_path=None, user_id=None, logo_key=None):
    """
    Brand Layout: Light gray top, Dark footer. Logo prominent.
    Top: Logo (if avail) + Address
    Middle: QR
    Bottom: Dark Footer with Agent Info
    """
    COLOR_BG = (0.97, 0.97, 0.97) # Light Gray
    COLOR_FOOTER = hex_to_rgb(sign_color) # Use selected color for footer background
    COLOR_TEXT = (0.1, 0.1, 0.1)
    
    # 1. Background
    c.setFillColorRGB(*COLOR_BG)
    c.rect(-layout.bleed, -layout.bleed, layout.width + 2*layout.bleed, layout.height + 2*layout.bleed, fill=1, stroke=0)
    
    # 2. Footer (Bottom 20%)
    footer_h = layout.height * 0.22
    c.setFillColorRGB(*COLOR_FOOTER)
    c.rect(-layout.bleed, -layout.bleed, layout.width + 2*layout.bleed, footer_h + layout.bleed, fill=1, stroke=0)
    
    # 3. Logo (Top Center)
    storage = get_storage()
    has_logo = False
    cursor_y = layout.height * 0.92
    
    logo_size = layout.height * 0.15
    if logo_key and storage.exists(logo_key):
        try:
            logo_data = storage.get_file(logo_key)
            img = ImageReader(logo_data)
            # Draw centered
            logo_x = (layout.width - logo_size) / 2
            logo_y = cursor_y - logo_size
            c.drawImage(img, logo_x, logo_y, width=logo_size, height=logo_size, preserveAspectRatio=True, mask='auto', anchorAtXY=True)
            cursor_y -= (logo_size + layout.margin * 0.5)
            has_logo = True
        except: pass
        
    if not has_logo:
        # Fallback text
        c.setFont("Helvetica-Bold", layout.agent_name_font)
        c.setFillColorRGB(*COLOR_TEXT)
        c.drawCentredString(layout.width/2, cursor_y, brokerage.upper())
        cursor_y -= (layout.agent_name_font * 2)

    # 4. Address & Price (Below Logo)
    c.setFont("Helvetica-Bold", layout.address_font)
    c.setFillColorRGB(*COLOR_TEXT)
    c.drawCentredString(layout.width/2, cursor_y, address.upper())
    cursor_y -= (layout.address_font * 1.5)
    
    if price:
        c.setFont("Helvetica-Bold", layout.price_font)
        c.setFillColorRGB(*hex_to_rgb(sign_color))
        c.drawCentredString(layout.width/2, cursor_y, price)
        cursor_y -= (layout.price_font * 1.2)

    # 5. QR Code (Middle-Bottom, above footer)
    # Available vertical space: cursor_y down to footer_h
    qr_space_h = cursor_y - footer_h - layout.margin
    qr_size = min(layout.width * 0.5, qr_space_h)
    
    qr_x = (layout.width - qr_size) / 2
    qr_y = footer_h + (qr_space_h - qr_size) / 2
    
    if qr_value:
        qr_url = qr_value
    else:
        qr_url = "https://example.com"
        
    try:
        draw_qr(c, qr_url, qr_x, qr_y, qr_size, user_id=user_id)
    except: pass

    # 6. Agent Info (In Footer, White Text)
    c.setFillColorRGB(1, 1, 1)
    
    # Agent Name
    name_y = footer_h * 0.65
    c.setFont("Helvetica-Bold", layout.agent_name_font)
    c.drawCentredString(layout.width/2, name_y, agent_name.upper())

    # Phone / Email
    sub_y = footer_h * 0.35
    c.setFont("Helvetica", layout.agent_sub_font)
    c.drawCentredString(layout.width/2, sub_y, f"{agent_phone}  |  {agent_email.lower()}")


def _draw_landscape_minimal(c, layout, address, beds, baths, sqft, price,
                        agent_name, brokerage, agent_email, agent_phone,
                        qr_key, agent_photo_key, sign_color, qr_value=None,
                        agent_photo_path=None, user_id=None, logo_key=None):
    """
    Minimalist Layout (Landscape): White background, Large QR LEFT, Text RIGHT.
    Split 40/60 roughly.
    """
    COLOR_TEXT = (0, 0, 0)
    COLOR_SUBTEXT = (0.5, 0.5, 0.5)
    
    # 1. Background
    c.setFillColorRGB(1, 1, 1)
    c.rect(-layout.bleed, -layout.bleed, layout.width + 2*layout.bleed, layout.height + 2*layout.bleed, fill=1, stroke=0)
    
    # Grid
    margin_x = layout.width * 0.05
    margin_y = layout.height * 0.1
    
    # Left Block: QR Code (40% width)
    left_w = layout.width * 0.4
    qr_size = min(left_w, layout.height - 2*margin_y)
    
    qr_x = margin_x + (left_w - qr_size) / 2
    qr_y = (layout.height - qr_size) / 2
    
    if qr_value: qr_url = qr_value
    elif qr_key:
        filename = os.path.basename(qr_key)
        code_part = os.path.splitext(filename)[0]
        qr_url = property_scan_url(PUBLIC_BASE_URL, code_part)
    else: qr_url = "https://example.com"

    try:
        draw_qr(c, qr_url, qr_x, qr_y, qr_size, ecc_level="H", user_id=user_id)
        # Scan me text
        c.setFont("Helvetica-Bold", layout.features_font * 0.8)
        c.setFillColorRGB(*COLOR_TEXT)
        c.drawCentredString(qr_x + qr_size/2, qr_y - (layout.features_font * 1.5), "SCAN FOR PHOTOS")
    except: pass
    
    # Right Block: Info (starts at 45%)
    right_x = layout.width * 0.45
    
    # Vertically centered block in right side
    # Address -> Price -> Features -> Divider -> Agent
    
    y_cursor = layout.height * 0.75
    
    # Address
    c.setFont("Helvetica-Bold", layout.address_font * 1.2)
    c.setFillColorRGB(*COLOR_TEXT)
    c.drawString(right_x, y_cursor, address.upper())
    y_cursor -= (layout.address_font * 1.6)
    
    # Price
    if price:
        c.setFont("Helvetica-Bold", layout.price_font * 1.2)
        c.setFillColorRGB(*hex_to_rgb(sign_color))
        c.drawString(right_x, y_cursor, price)
        y_cursor -= (layout.price_font * 1.5)
        
    # Features
    c.setFont("Helvetica", layout.features_font * 1.3)
    c.setFillColorRGB(*COLOR_SUBTEXT)
    line = f"{beds} BEDS  |  {baths} BATHS"
    if sqft: line += f"  |  {sqft} SQ FT"
    c.drawString(right_x, y_cursor, line)
    
    # Divider
    y_cursor -= (layout.height * 0.15)
    c.setStrokeColorRGB(0.9, 0.9, 0.9)
    c.setLineWidth(2)
    c.line(right_x, y_cursor, layout.width - margin_x, y_cursor)
    
    # Agent
    y_cursor -= (layout.height * 0.1)
    c.setFont("Helvetica-Bold", layout.agent_name_font)
    c.setFillColorRGB(*COLOR_TEXT)
    c.drawString(right_x, y_cursor, f"{agent_name.upper()} | {brokerage.upper()}")
    
    y_cursor -= (layout.agent_name_font * 1.3)
    c.setFont("Helvetica", layout.agent_sub_font)
    c.drawString(right_x, y_cursor, f"{agent_phone}  |  {agent_email.lower()}")


def _draw_landscape_brand(c, layout, address, beds, baths, sqft, price,
                        agent_name, brokerage, agent_email, agent_phone,
                        qr_key, agent_photo_key, sign_color, qr_value=None,
                        agent_photo_path=None, user_id=None, logo_key=None):
    """
    Brand Layout (Landscape):
    Sidebar (Left 25%) with Logo/Brand color.
    Content (Right 75%) with Clean info and QR.
    """
    COLOR_TEXT = (0.1, 0.1, 0.1)
    COLOR_BG = (1, 1, 1) # White Content Area
    COLOR_SIDEBAR = hex_to_rgb(sign_color) # Sidebar matches brand
    
    # 1. Background Content
    c.setFillColorRGB(*COLOR_BG)
    c.rect(-layout.bleed, -layout.bleed, layout.width + 2*layout.bleed, layout.height + 2*layout.bleed, fill=1, stroke=0)
    
    # 2. Sidebar (Left)
    sidebar_w = layout.width * 0.28
    c.setFillColorRGB(*COLOR_SIDEBAR)
    c.rect(-layout.bleed, -layout.bleed, sidebar_w + layout.bleed, layout.height + 2*layout.bleed, fill=1, stroke=0)
    
    # 3. Sidebar Content (Logo + Agent)
    storage = get_storage()
    
    # Logo (Top of Sidebar)
    logo_y = layout.height * 0.75
    logo_size = sidebar_w * 0.7
    logo_x = (sidebar_w - logo_size) / 2
    
    has_logo = False
    if logo_key and storage.exists(logo_key):
        try:
            logo_data = storage.get_file(logo_key)
            img = ImageReader(logo_data)
            c.drawImage(img, logo_x, logo_y, width=logo_size, height=logo_size, preserveAspectRatio=True, mask='auto', anchorAtXY=True)
            has_logo = True
        except: pass
        
    if not has_logo:
        # Text fallback
        c.setFillColorRGB(1, 1, 1)
        c.setFont("Helvetica-Bold", layout.agent_name_font)
        c.drawCentredString(sidebar_w/2, logo_y, "BRAND")
        
    # Agent Info Bottom Sidebar
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", layout.agent_name_font)
    c.drawCentredString(sidebar_w/2, layout.height * 0.25, agent_name.upper())
    
    c.setFont("Helvetica", layout.agent_sub_font * 0.9)
    c.drawCentredString(sidebar_w/2, layout.height * 0.18, brokerage.upper())
    c.drawCentredString(sidebar_w/2, layout.height * 0.12, agent_phone)
    
    # 4. Main Content (Right)
    # 3 cols: Info | Info | QR
    content_x = sidebar_w + (layout.width * 0.05)
    content_w = layout.width - content_x - (layout.width * 0.05)
    
    cursor_y = layout.height * 0.85
    
    # Address
    c.setFillColorRGB(*COLOR_TEXT)
    c.setFont("Helvetica-Bold", layout.address_font * 1.2)
    c.drawString(content_x, cursor_y, address.upper())
    
    cursor_y -= (layout.address_font * 1.5)
    
    # Price
    if price:
        c.setFillColorRGB(*COLOR_SIDEBAR) # Use brand color
        c.setFont("Helvetica-Bold", layout.price_font * 1.2)
        c.drawString(content_x, cursor_y, price)
        cursor_y -= (layout.price_font * 1.5)

    # Features
    c.setFillColorRGB(0.5, 0.5, 0.5)
    c.setFont("Helvetica", layout.features_font * 1.3)
    line = f"{beds} BEDS | {baths} BATHS"
    if sqft: line += f" | {sqft} SQ FT"
    c.drawString(content_x, cursor_y, line)
    
    # 5. QR Code (Bottom Right of Content Area)
    qr_size = layout.height * 0.45
    qr_x = layout.width - (layout.width * 0.05) - qr_size
    qr_y = layout.height * 0.1
    
    if qr_value: qr_url = qr_value
    else: qr_url = "https://example.com"
    
    try:
        draw_qr(c, qr_url, qr_x, qr_y, qr_size, user_id=user_id)
        # Scan CTA
        c.setFillColorRGB(*COLOR_TEXT)
        c.setFont("Helvetica-Bold", layout.features_font)
        c.drawCentredString(qr_x + qr_size/2, qr_y - (layout.features_font * 1.2), "SCAN FOR PHOTOS")
    except: pass


def _draw_modern_round_layout(
    c,
    layout,
    address,
    beds=None,
    baths=None,
    sqft=None,
    price=None,
    agent_name=None,
    brokerage=None,
    agent_email=None,
    agent_phone=None,
    qr_key=None,
    agent_photo_key=None,
    sign_color=None,
    qr_value=None,
    agent_photo_path=None,
    user_id=None,
    logo_key=None,
    **kwargs,
):
    """
    Dispatcher for Modern Round Layout (Portrait vs Landscape).
    Ensures deliberate composition for each orientation.
    """
    if layout.width > layout.height:
        _draw_modern_round_landscape(c, layout, address, beds, baths, sqft, price,
                                     agent_name, brokerage, agent_email, agent_phone,
                                     qr_key, agent_photo_key, sign_color, qr_value,
                                     agent_photo_path, user_id, logo_key)
    else:
        _draw_modern_round_portrait(c, layout, address, beds, baths, sqft, price,
                                    agent_name, brokerage, agent_email, agent_phone,
                                    qr_key, agent_photo_key, sign_color, qr_value,
                                    agent_photo_path, user_id, logo_key)

def _draw_modern_round_portrait(c, layout, address, beds, baths, sqft, price,
                                agent_name, brokerage, agent_email, agent_phone,
                                qr_key, agent_photo_key, sign_color, qr_value=None,
                                agent_photo_path=None, user_id=None, logo_key=None):
    """
    Portrait Implementation:
    - Stacked Hierarchy: Address > Features > Price > QR > Identity
    - Safe Margins preserved
    """
    COLOR_ACCENT = hex_to_rgb(sign_color)
    COLOR_TEXT = (0.1, 0.1, 0.1)
    COLOR_SUBTEXT = (0.4, 0.4, 0.4)
    COLOR_BG = (1, 1, 1)

    # 1. Background
    c.setFillColorRGB(*COLOR_BG)
    c.rect(-layout.bleed, -layout.bleed, 
           layout.width + 2*layout.bleed, 
           layout.height + 2*layout.bleed, 
           fill=1, stroke=0)

    # 2. Header (Address) - Hero
    c.setFillColorRGB(*COLOR_TEXT)
    
    # Calculate usable width
    content_width = layout.width - (2 * SAFE_MARGIN)
    
    # Address at top (10% padding from top margin)
    addr_y = layout.height - SAFE_MARGIN - SPACING['md']
    
    # Measure and draw address (Max 2 lines)
    pdf_text.draw_fitted_block(
        c, address.upper(),
        SAFE_MARGIN, addr_y - (layout.address_font * 2), # Approx height
        content_width, layout.address_font * 2.5,
        FONT_BOLD, layout.address_font, min_font_size=TYPE_SCALE_MODERN['address']['min'],
        align='center', max_lines=2
    )

    # 3. Features (Below Address)
    features_y = addr_y - (layout.address_font * 2.5) - SPACING['sm']
    features_parts = []
    if beds: features_parts.append(f"{beds} BEDS")
    if baths: features_parts.append(f"{baths} BATHS")
    if sqft: features_parts.append(f"{sqft} SQ FT")
    
    if features_parts:
        features_line = "  •  ".join(features_parts)
        c.setFillColorRGB(*COLOR_SUBTEXT)
        pdf_text.draw_single_line_fitted(
            c, features_line,
            layout.width / 2, features_y,
            content_width,
            FONT_MED, layout.features_font, min_font_size=TYPE_SCALE_MODERN['features']['min']
        )

    # 4. Price (Pill below features)
    price_y = features_y - layout.features_font - SPACING['md']
    if price:
        display_price = price if "$" in str(price) else f"${price}"
        
        # Calculate fit
        font_sz = pdf_text.fit_font_size_single_line(
            display_price, FONT_BOLD, 
            content_width * 0.6, TYPE_SCALE_MODERN['price']['max'], 
            min_font_size=TYPE_SCALE_MODERN['price']['min']
        )
        
        # Pill Dimensions
        c.setFont(FONT_BOLD, font_sz)
        p_w = c.stringWidth(display_price, FONT_BOLD, font_sz)
        pill_pad_x = SPACING['sm'] * 2
        pill_pad_y = SPACING['xs'] * 1.5
        pill_w = p_w + (pill_pad_x * 2)
        pill_h = font_sz + (pill_pad_y * 2)
        
        # Background
        c.setFillColorRGB(*COLOR_ACCENT)
        # Center pill
        pill_x = (layout.width - pill_w) / 2
        pill_y_bottom = price_y - (pill_h / 2)
        c.roundRect(pill_x, pill_y_bottom, pill_w, pill_h, pill_h/2, fill=1, stroke=0)
        
        # Text
        c.setFillColorRGB(1, 1, 1)
        c.drawCentredString(layout.width / 2, price_y - (font_sz * 0.35), display_price)

    # 5. QR Code (Center-Bottom)
    # Available vertical space: Price bottom to Footer top
    footer_top = layout.footer_height + SAFE_MARGIN
    qr_area_top = price_y - SPACING['lg']
    qr_center_y = (qr_area_top + footer_top) / 2
    
    # Ensure min size and safe margins
    max_qr_h = qr_area_top - footer_top - SPACING['md']
    qr_size = min(layout.width * 0.6, max_qr_h, QR_MIN_SIZE * 2.0) # Cap at decent size
    
    # Ring
    c.setFillColorRGB(*COLOR_ACCENT)
    c.circle(layout.width / 2, qr_center_y, (qr_size/2) * 1.15, fill=1, stroke=0)
    c.setFillColorRGB(1, 1, 1)
    c.circle(layout.width / 2, qr_center_y, (qr_size/2) * 1.05, fill=1, stroke=0)
    
    qr_url = resolve_qr_url(qr_value, qr_key)
    qr_x = (layout.width - qr_size) / 2
    qr_y_pos = qr_center_y - (qr_size / 2)
    
    safe_draw_qr(c, qr_url, qr_x, qr_y_pos, qr_size, user_id)

    # 6. Identity Footer
    asset = {
        'brand_name': agent_name,
        'brokerage_name': brokerage,
        'email': agent_email,
        'phone': agent_phone,
        'headshot_key': agent_photo_key,
        'logo_key': logo_key,
        'agent_headshot_path': agent_photo_path,
    }
    draw_identity_block(
        c,
        0, 0,
        layout.width, layout.footer_height,
        asset,
        get_storage(),
        theme='dark',
        cta_text="SCAN FOR DETAILS",
    )

def _draw_modern_round_landscape(c, layout, address, beds, baths, sqft, price,
                                 agent_name, brokerage, agent_email, agent_phone,
                                 qr_key, agent_photo_key, sign_color, qr_value=None,
                                 agent_photo_path=None, user_id=None, logo_key=None):
    """
    Landscape Implementation:
    - 2-Column Grid
    - Left (60%): Address, Features, Price, Agent info
    - Right (40%): Massive QR, CTA
    """
    COLOR_ACCENT = hex_to_rgb(sign_color)
    COLOR_TEXT = (0.1, 0.1, 0.1)
    COLOR_BG = (1, 1, 1)
    
    c.setFillColorRGB(*COLOR_BG)
    c.rect(-layout.bleed, -layout.bleed, 
           layout.width + 2*layout.bleed, 
           layout.height + 2*layout.bleed, fill=1, stroke=0)
           
    band_h = layout.footer_height
    body_top = layout.height - SAFE_MARGIN
    body_bottom = band_h + SAFE_MARGIN
    content_w = layout.width - (2 * SAFE_MARGIN)
    content_h = max(0, body_top - body_bottom)
    
    col_gap = SPACING['lg']
    left_col_w = (content_w * 0.6) - (col_gap / 2)
    right_col_w = (content_w * 0.4) - (col_gap / 2)
    
    left_x = SAFE_MARGIN
    right_x = SAFE_MARGIN + left_col_w + col_gap
    
    # --- Left Column (Info) ---
    c.setFillColorRGB(*COLOR_TEXT)
    
    # Address (Top Left)
    addr_y = layout.height - SAFE_MARGIN - SPACING['sm']
    pdf_text.draw_fitted_block(
        c, address.upper(),
        left_x, addr_y - (layout.address_font * 2.5),
        left_col_w, layout.address_font * 3.0,
        FONT_BOLD, layout.address_font * 1.2, min_font_size=TYPE_SCALE_MODERN['address']['min'],
        align='left', max_lines=2
    )
    
    # Features (Below Address)
    features_y = addr_y - (layout.address_font * 2.5)
    features_parts = []
    if beds: features_parts.append(f"{beds} BEDS")
    if baths: features_parts.append(f"{baths} BATHS")
    if sqft: features_parts.append(f"{sqft} SQ FT")
    
    if features_parts:
        features_line = "  •  ".join(features_parts)
        c.setFillColorRGB(*hex_to_rgb(sign_color)) # Accent color for features in landscape
        pdf_text.draw_fitted_block(
            c, features_line,
            left_x, features_y - layout.features_font,
            left_col_w, layout.features_font * 1.5,
            FONT_MED, layout.features_font, min_font_size=TYPE_SCALE_MODERN['features']['min'],
            align='left', max_lines=1
        )

    # Price (Below Features)
    price_y = features_y - (layout.features_font * 2)
    if price:
        display_price = price if "$" in str(price) else f"${price}"
        c.setFillColorRGB(*COLOR_TEXT)
        # Just text, large and bold
        pdf_text.draw_fitted_block(
            c, display_price,
            left_x, price_y - layout.price_font,
            left_col_w, layout.price_font * 1.5,
            FONT_BOLD, layout.price_font, min_font_size=TYPE_SCALE_MODERN['price']['min'],
            align='left', max_lines=1
        )

    # Identity (Bottom Left)
    asset = {
        'brand_name': agent_name,
        'brokerage_name': brokerage,
        'email': agent_email,
        'phone': agent_phone,
        'headshot_key': agent_photo_key,
        'logo_key': logo_key,
        'agent_headshot_path': agent_photo_path,
    }
    draw_identity_block(
        c,
        0, 0,
        layout.width, band_h,
        asset,
        get_storage(),
        theme='dark',
        cta_text="SCAN FOR DETAILS",
    )

    # --- Right Column (QR Focus) ---
    # Center QR vertically in available space
    qr_center_x = right_x + (right_col_w / 2)
    qr_center_y = (body_top + body_bottom) / 2
    
    qr_size = min(right_col_w, content_h * 0.7)
    
    # Accent Ring
    c.setFillColorRGB(*COLOR_ACCENT)
    c.circle(qr_center_x, qr_center_y, (qr_size/2)*1.1, fill=1, stroke=0)
    c.setFillColorRGB(1, 1, 1)
    c.circle(qr_center_x, qr_center_y, (qr_size/2)*1.02, fill=1, stroke=0)
    
    qr_url = resolve_qr_url(qr_value, qr_key)
    safe_draw_qr(c, qr_url, qr_center_x - qr_size/2, qr_center_y - qr_size/2, qr_size, user_id)

def _draw_modern_footer(c, layout, agent, brokerage, phone, color_hex):
    """Standard Portrait Footer"""
    x = SAFE_MARGIN
    w = layout.width - (2 * SAFE_MARGIN)
    y_top = layout.footer_height
    y_line = y_top - SPACING['sm']
    
    # Divisor line
    c.setStrokeColorRGB(0.8, 0.8, 0.8)
    c.setLineWidth(1)
    c.line(x, y_line, x+w, y_line)
    
    # Text
    c.setFillColorRGB(0.2, 0.2, 0.2)
    # Stacked: Agent Name (Bold), Brokerage (Reg), Phone (Small)?
    # Or Agent (Left), Brokerage (Right)
    
    # Left: Agent
    pdf_text.draw_fitted_block(
        c, agent.upper(),
        x, 0, w * 0.5, y_line - SPACING['xs'],
        FONT_BOLD, 36, min_font_size=12, align='left', max_lines=1
    )
    
    # Right: Brokerage
    pdf_text.draw_fitted_block(
        c, brokerage.upper(),
        x + w*0.5, 0, w * 0.5, y_line - SPACING['xs'],
        FONT_BODY, 24, min_font_size=10, align='right', max_lines=1
    )

def _draw_modern_footer_landscape(c, layout, agent, brokerage, phone, x, w):
    """Landscape Footer (Bottom Left Column)"""
    y_bottom = SAFE_MARGIN
    
    # Agent Name
    pdf_text.draw_fitted_block(
        c, agent.upper(),
        x, y_bottom + 30, w, 40,
        FONT_BOLD, 32, min_font_size=16, align='left', max_lines=1
    )
    
    # Brokerage
    pdf_text.draw_fitted_block(
        c, brokerage.upper(),
        x, y_bottom, w, 30,
        FONT_BODY, 24, min_font_size=12, align='left', max_lines=1
    )

def resolve_qr_url(val, key):
    if val: return val
    if key:
        filename = os.path.basename(key)
        code = os.path.splitext(filename)[0]
        return property_scan_url(PUBLIC_BASE_URL, code)
    return "https://example.com"

def safe_draw_qr(c, url, x, y, size, uid):
    try:
        draw_qr(c, url, x, y, size, user_id=uid, ecc_level="H")
    except Exception as e:
        logger.error(f"QR Error: {e}")
