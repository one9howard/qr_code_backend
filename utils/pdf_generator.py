"""
PDF Sign Generator with Size-Aware Layout.
Generates print-ready PDF signs that scale proportionally to any supported size.
Vector QR codes for print-grade sharpness using ReportLab's QrCodeWidget.
"""
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import inch
from reportlab.lib.utils import ImageReader
import os
import io
from constants import SIGN_SIZES, DEFAULT_SIGN_COLOR, DEFAULT_SIGN_SIZE
from utils.qr_vector import draw_vector_qr
from utils.storage import get_storage
from config import BASE_URL

class LayoutSpec:
    """
    Proportional layout specification derived from page dimensions.
    All values are in points (1 inch = 72 points).
    """
    def __init__(self, width_in: float, height_in: float):
        self.width = width_in * inch
        self.height = height_in * inch
        
        # Base unit for proportional scaling
        min_dim = min(self.width, self.height)
        
        # Bleed (standard 0.125")
        self.bleed = 0.125 * inch
        
        # Margins (proportional to min dimension) - print-safe
        self.margin = 0.07 * min_dim  # Increased for print-safe edges
        
        # Font sizes (proportional with clamps) - INCREASED for print legibility
        # Scaling factors increased by ~20-25% from original values
        self.address_font = max(24, min(72, 0.054 * self.width))
        self.features_font = max(16, min(48, 0.036 * self.width))
        self.price_font = max(34, min(96, 0.072 * self.width))
        self.agent_name_font = max(18, min(48, 0.036 * self.width))
        self.agent_sub_font = max(14, min(38, 0.029 * self.width))
        
        # QR Code base size (will be recomputed dynamically in _draw_standard_layout)
        # This is a starting point, actual size computed with quiet zones
        self.qr_size_base = min(0.5 * min_dim, 0.6 * self.height - self.margin * 6)
        self.qr_size = self.qr_size_base  # Legacy compatibility
        
        # Banner height (proportional to height)
        self.banner_height = 0.25 * self.height
        
        # Agent photo size (proportional to banner)
        self.photo_size = 0.7 * self.banner_height
        
        # Vertical positions (from top, proportional)
        self.address_y = self.height - (0.1 * self.height)
        self.features_y = self.height - (0.17 * self.height)
        
        # QR positioned in center area (base, may be adjusted)
        self.qr_y = self.height - (0.22 * self.height) - self.qr_size
        
        # Price just below QR
        self.price_y = self.qr_y - (0.04 * self.height)


# =============================================================================
# QR Drawing Helper (Switchable Vector/Raster)
# =============================================================================
from utils.qr_vector import draw_vector_qr
from utils.qr_image import render_qr_png
from services.branding import get_user_qr_logo_bytes
from config import ENABLE_QR_LOGO
from reportlab.lib.utils import ImageReader
import io

logger = logging.getLogger(__name__)

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
            logo_bytes = get_user_qr_logo_bytes(user_id)
            if logo_bytes:
                # Render High-Res Raster
                # Resolution: target at least 1024px, or 10x size in points if larger?
                # 1024px is usually plenty for signs (300dpi @ 3 inches = 900px)
                # Let's ensure at least 10 pixels per point density if size is huge?
                # standard 1024 is safe default.
                
                png_data = render_qr_png(qr_value, size_px=1024, logo_png=logo_bytes)
                
                # ReportLab drawImage
                # c.drawImage(image, x, y, width=None, height=None)
                # Need ImageReader
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
                      user_id=None):
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
    """
    # Explicit legacy mode detection:
    # - order_id is None (local tooling like generate_sample_pdfs.py)
    # - return_path=True explicitly set
    # - qr_path provided (legacy test pattern)
    # - agent_photo_path provided (legacy test pattern)
    legacy_mode = (order_id is None) or return_path or (qr_path is not None) or (agent_photo_path is not None)
    
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
        
        if is_landscape:
            _draw_landscape_split_layout(
                c, layout, address, beds, baths, sqft, price,
                agent_name, brokerage, agent_email, agent_phone,
                qr_key, agent_photo_key, sign_color, qr_value=qr_value,
                agent_photo_path=agent_photo_path, user_id=user_id
            )
        else:
            _draw_standard_layout(
                c, layout, address, beds, baths, sqft, price,
                agent_name, brokerage, agent_email, agent_phone,
                qr_key, agent_photo_key, sign_color, qr_value=qr_value,
                agent_photo_path=agent_photo_path, user_id=user_id
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
                          agent_photo_path=None):
    """Standard centered layout for vertical/poster signs."""
    
    # Colors
    COLOR_ORANGE = (212/255, 93/255, 18/255)
    COLOR_BANNER = hex_to_rgb(sign_color)
    
    # 1. Address (Top)
    c.setFont("Helvetica-Bold", layout.address_font)
    c.setFillColorRGB(0, 0, 0)
    c.drawCentredString(layout.width / 2, layout.address_y, address.upper())
    
    # 2. Features line
    c.setFont("Helvetica", layout.features_font)
    c.setFillColorRGB(0.5, 0.5, 0.5)
    features_line = f"{beds} BEDS | {baths} BATHS"
    if sqft:
        features_line += f" | {sqft} SQ FT"
    c.drawCentredString(layout.width / 2, layout.features_y, features_line)
    
    # =====================================================
    # 3. QR Code with Quiet Zone - VECTOR RENDERING
    # =====================================================
    # Use vector QR for print-grade sharpness (no raster scaling)
    try:
        # Calculate quiet zone (2% of min dimension, at least 0.25")
        quiet = max(0.02 * min(layout.width, layout.height), 0.25 * inch)
        
        # Calculate vertical safe region for QR
        # Top limit: below features line with quiet zone
        qr_top_limit = layout.features_y - quiet - (layout.features_font * 1.2)
        
        # CTA Font Size
        cta_font_size = layout.price_font * 0.35
        cta_height = cta_font_size * 1.2
        
        # Bottom limit: above banner with quiet zone, reserve space for price AND CTA
        price_block_height = (layout.price_font * 1.5 + quiet + cta_height) if price else (quiet + cta_height)
        qr_bottom_limit = layout.banner_height + quiet + price_block_height
        
        # Calculate available space 
        qr_max_h = qr_top_limit - qr_bottom_limit
        qr_max_w = layout.width - 2 * (layout.margin + quiet)
        
        # Target: 25% larger than base, but clamped to available space
        qr_target = layout.qr_size_base * 1.25
        qr_size = max(0.5 * inch, min(qr_target, qr_max_w, qr_max_h))
        
        # Position QR centered horizontally
        qr_x = (layout.width - qr_size) / 2
        
        # Position QR vertically: center in available region
        available_center = (qr_top_limit + qr_bottom_limit) / 2
        qr_y = available_center - (qr_size / 2)
        
        # Clamp to safe bounds
        qr_y = max(qr_bottom_limit, min(qr_y, qr_top_limit - qr_size))
        
        # =====================================================
        # PREFLIGHT VALIDATION (New)
        # =====================================================
        from utils.print_preflight import validate_sign_layout, PreflightError
        
        # Validate the specific instance of QR size/quiet zone we just calculated
        pf_result = validate_sign_layout(layout, "standard", qr_size, quiet)
        
        # Log warnings
        for warn in pf_result.warnings:
            print(f"[PREFLIGHT WARNING] {warn}")
            
        # Hard fail on errors (unless overridden, but we want safe defaults)
        if not pf_result.ok:
            print(f"[PREFLIGHT ERROR] Validation failed: {pf_result.errors}")
            # Raise exception to abort generation - do not print bad signs
            raise PreflightError(pf_result)
        
        # Determine QR URL: prefer qr_value parameter, fallback to extracting from qr_key
        if qr_value:
            qr_url = qr_value
        elif qr_key:
            # Extract qr_code from path pattern: qr/{qr_code_value}.png or similar
            # Be robust to full keys like "staging/qr/foo.png" or "qr/foo.png"
            filename = os.path.basename(qr_key)
            qr_code_value = os.path.splitext(filename)[0]
            qr_url = f"{BASE_URL.rstrip('/')}/r/{qr_code_value}"
        else:
            qr_url = "https://example.com"  # Fallback
        
        # Draw vector QR (print-grade, no raster scaling)
        draw_qr(c, qr_url, qr_x, qr_y, qr_size, quiet=quiet, ecc_level="H", user_id=user_id)
        
        # Draw CTA below QR
        c.setFont("Helvetica-Bold", cta_font_size)
        c.setFillColorRGB(0, 0, 0)
        cta_y = qr_y - (cta_font_size * 1.2)
        c.drawCentredString(layout.width / 2, cta_y, "SCAN FOR PHOTOS & DETAILS")
        
        # Update price position based on actual QR position - add extra padding
        dynamic_price_y = cta_y - quiet - (layout.price_font * 0.8)
        
    except Exception as e:
        # Re-raise preflight errors, swallow others (fallback logic handles others)
        if "Preflight failed" in str(e):
            raise
        print(f"[PDF] Error drawing vector QR code: {e}")
        qr_y = layout.qr_y  # Fallback
        dynamic_price_y = layout.price_y
    else:
        pass  # qr_y and dynamic_price_y already set
    
    # 4. Price (Below QR with quiet zone)
    if price:
        display_price = price if "$" in str(price) else f"${price}"
        c.setFont("Helvetica-Bold", layout.price_font)
        c.setFillColorRGB(*COLOR_ORANGE)
        # Clamp price_y above banner
        final_price_y = max(dynamic_price_y, layout.banner_height + 0.1 * inch)
        c.drawCentredString(layout.width / 2, final_price_y, display_price)
    
    # 5. Banner (Bottom)
    c.setFillColorRGB(*COLOR_BANNER)
    c.rect(-layout.bleed, -layout.bleed, 
           layout.width + 2 * layout.bleed, 
           layout.banner_height + layout.bleed, 
           fill=1, stroke=0)
    
    # =====================================================
    # 6. Agent Info - Headshot positioned further LEFT
    # =====================================================
    c.setFillColorRGB(1, 1, 1)  # White text
    
    agent_main = agent_name.upper()
    if brokerage:
        agent_main += f" | {brokerage.upper()}"
    agent_sub = f"{agent_email.lower()} | {agent_phone}"
    
    # Calculate text positions
    text_center_y = layout.banner_height / 2
    
    # Load Agent Photo - prefer filesystem path (legacy) over storage key (new)
    storage = get_storage()
    has_photo = False
    photo = None
    
    # Legacy mode: load from filesystem path
    if agent_photo_path and os.path.exists(agent_photo_path):
        try:
            photo = ImageReader(agent_photo_path)
            has_photo = True
        except Exception as e:
            print(f"[PDF] Error loading agent photo from path: {e}")
    # New mode: load from storage
    elif agent_photo_key and storage.exists(agent_photo_key):
        try:
            photo_bytes = storage.get_file(agent_photo_key)
            photo = ImageReader(photo_bytes)
            has_photo = True
        except Exception as e:
            print(f"[PDF] Error loading agent photo from storage: {e}")
    
    if has_photo and photo:
        # Position photo at LEFT margin (not centered)
        agent_block_left = layout.margin * 0.8  # Anchor to left
        photo_x = agent_block_left
        photo_y = (layout.banner_height - layout.photo_size) / 2
        
        try:
            c.drawImage(photo, photo_x, photo_y, 
                       width=layout.photo_size, height=layout.photo_size, mask='auto')
            
            # Text positioned right of photo with consistent gap
            text_x = photo_x + layout.photo_size + (0.025 * layout.width)
            
            # Calculate if text will overflow right edge
            max_text_width = layout.width - text_x - layout.margin
            
            # Measure text width and adjust font if needed
            name_font_size = layout.agent_name_font
            sub_font_size = layout.agent_sub_font
            
            c.setFont("Helvetica-Bold", name_font_size)
            name_width = c.stringWidth(agent_main, "Helvetica-Bold", name_font_size)
            
            # If text overflows, reduce font by up to 15%
            if name_width > max_text_width:
                scale_factor = max(0.85, max_text_width / name_width)
                name_font_size *= scale_factor
                sub_font_size *= scale_factor
            
            c.setFont("Helvetica-Bold", name_font_size)
            c.drawString(text_x, text_center_y + (0.05 * layout.banner_height), agent_main)
            c.setFont("Helvetica", sub_font_size)
            c.drawString(text_x, text_center_y - (0.15 * layout.banner_height), agent_sub)
        except Exception as e:
            print(f"[PDF] Error drawing agent photo: {e}")
            has_photo = False
    
    if not has_photo:
        _draw_centered_agent_info(c, layout, agent_main, agent_sub)


def _draw_landscape_split_layout(c, layout, address, beds, baths, sqft, price,
                                 agent_name, brokerage, agent_email, agent_phone,
                                 qr_key, agent_photo_key, sign_color, qr_value=None,
                                 agent_photo_path=None, user_id=None):
    """
    Split 50/50 Layout for Landscape Signs (36x18).
    Left: Agent Photo + Property Info + Contact
    Right: Massive QR Code
    """
    # Dimensions
    w = layout.width
    h = layout.height
    
    # Split
    mid_x = w * 0.5
    
    # Margins for content availability
    margin_x = w * 0.04  # Slightly reduced for more QR space
    margin_y = h * 0.06  # Slightly reduced for more QR space
    
    # Quiet zone for QR
    quiet = max(0.02 * h, 0.25 * inch)
    
    # Left Column Bounds
    left_x_start = margin_x
    left_x_end = mid_x - (margin_x * 0.5)
    left_w = left_x_end - left_x_start
    
    # Right Column Bounds
    right_x_start = mid_x + (margin_x * 0.5)
    right_x_end = w - margin_x
    right_w = right_x_end - right_x_start
    
    # Colors - Use sign_color for accents
    COLOR_ACCENT = hex_to_rgb(sign_color)
    COLOR_ORANGE = (212/255, 93/255, 18/255)
    COLOR_TEXT = (0, 0, 0)
    COLOR_SUBTEXT = (0.4, 0.4, 0.4)
    
    # =====================================================
    # ACCENT 1: Vertical Divider Bar at 50/50 split
    # =====================================================
    divider_width = max(3, min(8, 0.012 * w))  # 3-8 pts
    c.setFillColorRGB(*COLOR_ACCENT)
    c.rect(mid_x - divider_width/2, margin_y, divider_width, h - 2*margin_y, fill=1, stroke=0)
    
    # =====================================================
    # ACCENT 2: Border stroke around entire sign
    # =====================================================
    border_thickness = max(2, min(6, 0.004 * w))  # 2-6 pts
    c.setStrokeColorRGB(*COLOR_ACCENT)
    c.setLineWidth(border_thickness)
    c.rect(0, 0, w, h, fill=0, stroke=1)
    
    # =====================================================
    # RIGHT COLUMN: QR with VECTOR RENDERING
    # =====================================================
    try:
        # Maximize QR in the right column with quiet zone
        qr_max_w = right_w - 2 * quiet
        qr_max_h = h - 2 * quiet - margin_y  # Account for label space below
        qr_size = min(qr_max_w, qr_max_h)
        
        # Center QR in right column, slightly higher to leave room for label
        qr_x = right_x_start + (right_w - qr_size) / 2
        qr_y = (h - qr_size) / 2 + (0.02 * h)  # Slight upward offset for label
        
        # Determine QR URL: prefer qr_value, fallback to extracting from qr_key
        if qr_value:
            qr_url = qr_value
        elif qr_key:
            filename = os.path.basename(qr_key)
            qr_code_value = os.path.splitext(filename)[0]
            qr_url = f"{BASE_URL.rstrip('/')}/r/{qr_code_value}"
        else:
            qr_url = "https://example.com"  # Fallback
        
        # Draw vector QR (print-grade, no raster scaling)
        draw_qr(c, qr_url, qr_x, qr_y, qr_size, quiet=quiet, ecc_level="H", user_id=user_id)
        
        # Draw CTA below QR
        cta_font_size = layout.address_font * 0.4  # Proportional to address font
        c.setFont("Helvetica-Bold", cta_font_size)
        c.setFillColorRGB(*COLOR_TEXT)
        # Position below QR
        cta_y = qr_y - (cta_font_size * 1.5)
        c.drawCentredString(qr_x + qr_size/2, cta_y, "SCAN FOR PHOTOS & DETAILS")
        
    except Exception as e:
        print(f"[PDF] Split Layout Vector QR Error: {e}")

    # =====================================================
    # LEFT COLUMN: INFO
    # =====================================================
    cursor_y = h - margin_y

    # 1. Agent Headshot (Top Left of Left Col)
    # Increased by 20% (0.25 -> 0.30)
    photo_size = h * 0.30 
    
    storage = get_storage()
    if agent_photo_key and storage.exists(agent_photo_key):
        try:
            photo_bytes = storage.get_file(agent_photo_key)
            photo = ImageReader(photo_bytes)
            c.drawImage(photo, left_x_start, cursor_y - photo_size, 
                       width=photo_size, height=photo_size, mask='auto')
        except Exception as e:
            print(f"[PDF] Split Layout Photo Error: {e}")
            pass
    
    # Text starts to the right of photo
    text_x_start = left_x_start + photo_size + (w * 0.02)
    
    # Agent Name - Use sign_color
    c.setFont("Helvetica-Bold", layout.agent_name_font * 1.44)
    c.setFillColorRGB(*COLOR_ACCENT)  # Use customer-chosen color
    c.drawString(text_x_start, cursor_y - (photo_size * 0.3), agent_name.upper())
    
    # Brokerage
    c.setFont("Helvetica", layout.agent_sub_font * 1.2)
    c.setFillColorRGB(*COLOR_TEXT)
    c.drawString(text_x_start, cursor_y - (photo_size * 0.55), brokerage.upper())
    
    # Phone / Email
    c.setFont("Helvetica", layout.agent_sub_font * 1.1)
    c.setFillColorRGB(*COLOR_SUBTEXT)
    c.drawString(text_x_start, cursor_y - (photo_size * 0.75), agent_phone)
    c.drawString(text_x_start, cursor_y - (photo_size * 0.90), agent_email.lower())

    cursor_y -= (photo_size + h * 0.05)  # Move down past photo

    # 2. Property Info
    # Address
    c.setFont("Helvetica-Bold", layout.address_font * 1.1)
    c.setFillColorRGB(*COLOR_TEXT)
    c.drawString(left_x_start, cursor_y, address.upper())
    
    cursor_y -= (layout.address_font * 1.8)  # increased spacing

    # Price
    if price:
        display_price = price if "$" in str(price) else f"${price}"
        c.setFont("Helvetica-Bold", layout.price_font * 1.2)
        c.setFillColorRGB(*COLOR_ORANGE)
        c.drawString(left_x_start, cursor_y, display_price)
        cursor_y -= (layout.price_font * 1.44)

    # Features
    c.setFont("Helvetica", layout.features_font * 1.44)
    c.setFillColorRGB(*COLOR_SUBTEXT)
    features_line = f"{beds} BEDS | {baths} BATHS"
    if sqft:
        features_line += f" | {sqft} SQ FT"
    c.drawString(left_x_start, cursor_y, features_line)
    
    # =====================================================
    # ACCENT: Bottom border on agent/property side (left half)
    # =====================================================
    bottom_border_height = max(4, min(8, 0.008 * w))  # 4-8 pts
    c.setFillColorRGB(*COLOR_ACCENT)
    c.rect(0, 0, mid_x, bottom_border_height, fill=1, stroke=0)


def _draw_centered_agent_info(c, layout, agent_main, agent_sub):
    """Helper to draw centered agent info when no photo."""
    text_center_y = layout.banner_height / 2
    c.setFont("Helvetica-Bold", layout.agent_name_font)
    c.drawCentredString(layout.width / 2, text_center_y + (0.08 * layout.banner_height), agent_main)
    c.setFont("Helvetica", layout.agent_sub_font)
    c.drawCentredString(layout.width / 2, text_center_y - (0.12 * layout.banner_height), agent_sub)
