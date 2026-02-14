"""
Yard Sign PDF Generator

Generates print-ready PDFs for yard signs.
Always produces 2 pages (front/back) for double-sided printing.
Returns storage key (not local path).

Layout ID Mapping (legacy -> canonical):
  - listing_v2_phone_qr_premium -> yard_phone_qr_premium
  - listing_v2_address_qr_premium -> yard_address_qr_premium  
  - listing_modern_round -> yard_modern_round
  - listing_standard -> yard_standard
"""
import io
import logging
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from database import get_db
from utils.storage import get_storage
from utils.pdf_generator import LayoutSpec, SIGN_SIZES, DEFAULT_SIGN_SIZE, _draw_standard_layout, _draw_landscape_split_layout, _draw_modern_round_layout, hex_to_rgb
from utils.listing_designs import _draw_yard_phone_qr_premium, _draw_yard_address_qr_premium
from services.printing.layout_utils import register_fonts
from config import PUBLIC_BASE_URL
from utils.qr_urls import property_scan_url

logger = logging.getLogger(__name__)


def _format_price(price_val):
    """
    Safely format any price value for display on listing signs.
    Never throws - returns best-effort string.
    
    Examples:
        500000 -> "$500,000"
        "$1,250,000" -> "$1,250,000"
        "$500k" -> "$500k"
        "Call for price" -> "Call for price"
        None -> ""
    """
    if not price_val:
        return ""
    
    # Convert to string and strip whitespace
    price_str = str(price_val).strip()
    if not price_str:
        return ""
    
    # Check if it contains alphabetic characters (e.g. "k", "M", "Call")
    import re
    has_letters = bool(re.search(r'[a-zA-Z]', price_str))
    
    if has_letters:
        # Don't parse, just return cleaned string
        # Don't add $ if it doesn't look like a number
        return price_str
    
    # No letters - try to extract and format as number
    try:
        # Extract digits only (ignore $, commas, spaces)
        digits_only = re.sub(r'[^\d]', '', price_str)
        if digits_only:
            numeric_val = int(digits_only)
            return f"${numeric_val:,}"
        else:
            # No digits found, return original
            return price_str
    except (ValueError, OverflowError):
        return price_str


def generate_yard_sign_pdf(order, output_path=None, output_key=None):
    """
    Generate the print-ready PDF for a standard Yard Sign.
    
    Args:
        order (dict): Order details (address, QR data, agent info)
        output_path (str, optional): Local path to save. If None, saves to tmp.
        output_key (str, optional): Explicit storage key. If provided, overrides default naming.
        
    Returns:
        str: Storage key of the generated PDF (e.g. "pdfs/.../yard_sign_18x24.pdf")
    """
    register_fonts()
    db = get_db()
    storage = get_storage()
    
    # Handle both dict-like and object-like access
    def get_val(obj, key, default=None):
        if hasattr(obj, 'get'):
            return obj.get(key, default)
        return getattr(obj, key, default)
    
    order_id = get_val(order, 'id')
    property_id = get_val(order, 'property_id')
    user_id = get_val(order, 'user_id')
    
    # Fetch property data
    prop_row = db.execute(
        "SELECT * FROM properties WHERE id = %s", (property_id,)
    ).fetchone()
    
    if not prop_row:
        raise ValueError(f"Property {property_id} not found for order {order_id}")
    
    # Fetch agent data with correct schema columns
    agent_row = None
    agent_name = "Agent"
    brokerage = ""
    agent_phone = ""
    agent_email = ""
    
    if prop_row['agent_id']:
        agent_row = db.execute("""
            SELECT a.id, a.name as agent_name, a.brokerage, a.phone, a.email as agent_email,
                   a.photo_filename, a.logo_filename,
                   u.full_name, u.email as user_email
            FROM agents a 
            JOIN users u ON a.user_id = u.id 
            WHERE a.id = %s
        """, (prop_row['agent_id'],)).fetchone()
    
    if agent_row:
        # Agent display name priority: agents.name > users.full_name > "Agent"
        agent_name = agent_row.get('agent_name') or agent_row.get('full_name') or "Agent"
        brokerage = agent_row.get('brokerage') or ""
        agent_phone = agent_row.get('phone') or ""
        agent_email = agent_row.get('agent_email') or agent_row.get('user_email') or ""
    else:
        # Fallback to order user
        user_row = db.execute(
            "SELECT * FROM users WHERE id = %s", (user_id,)
        ).fetchone()
        if user_row:
            agent_name = user_row.get('full_name') or "Agent"
            agent_email = user_row.get('email') or ""

    if not prop_row:
        raise ValueError(f"Missing data for Order {order_id}")

    # Helper for safe dict access
    def get(row, k, default=''):
        return str(row[k]) if row and row.get(k) else default

    # Build data
    address = get(prop_row, 'address', 'Address TBD')
    beds = get(prop_row, 'beds', '0')
    baths = get(prop_row, 'baths', '0')
    sqft = get(prop_row, 'sqft', '')
    
    price_val = prop_row.get('price')
    price = _format_price(price_val)

    # Agent Assets
    agent_photo_key = agent_row.get('photo_filename') if agent_row else None
    agent_logo_key = agent_row.get('logo_filename') if agent_row else None
    
    # Sign config - use order's persisted color and size
    sign_color = get_val(order, 'sign_color') or '#0077ff'  # DEFAULT_SIGN_COLOR fallback
    sign_size = get_val(order, 'print_size') or get_val(order, 'sign_size') or '18x24'
    
    # QR URL
    # QR URL
    # Use canonical helper - strictly no /s/ allowed
    qr_code = prop_row.get('qr_code')
    if not qr_code:
        # Fallback if DB data bad (Phase 1 sanity)
        # Assuming we might need to generate one or fail?
        # For now, let's use the property ID if no code (legacy) but really we should fail if strictly Phase 1.
        # However, user spec says "Create single canonical helper ... use property.qr_code"
        # If property.qr_code is None, we have a data problem.
        # Let's assume property.qr_code exists or we rely on the helper to fail/be handled.
        # But wait, existing code used ID. The prompt says "use property.qr_code to build the QR URL".
        # Let's try to get 'qr_code' from prop_row.
        qr_code = prop_row.get('qr_code')
        if not qr_code:
             # Critical Failure for Phase 1
             raise ValueError(f"Property {prop_row['id']} has no qr_code. Cannot generate valid Yard Sign.")
    
    qr_url = property_scan_url(PUBLIC_BASE_URL, qr_code)
    
    # Layout config
    if sign_size not in SIGN_SIZES:
        sign_size = DEFAULT_SIGN_SIZE
    size_config = SIGN_SIZES[sign_size]
    layout = LayoutSpec(size_config['width_in'], size_config['height_in'])
    
    # Layout ID Dispatch
    layout_id = get_val(order, 'layout_id') or 'yard_modern_round'
    
    # Canonical Layout ID Mapping (accept legacy names, use canonical internally)
    LAYOUT_ALIASES = {
        'listing_standard': 'yard_modern_round',
        'yard_standard': 'yard_modern_round',
        'smart_v1_photo_banner': 'yard_modern_round',
        'listing_modern_round': 'yard_modern_round',
        'yard_modern_round': 'yard_modern_round',
    }
    
    if layout_id in LAYOUT_ALIASES:
        layout_id = LAYOUT_ALIASES[layout_id]

    # Generate PDF in memory
    pdf_buffer = io.BytesIO()
    c = canvas.Canvas(pdf_buffer, pagesize=(layout.width + 2*layout.bleed, layout.height + 2*layout.bleed))
    
    # Determine if landscape (width > height)
    is_landscape = size_config['width_in'] > size_config['height_in']
    
    # Draw 2 identical pages (front/back)
    for page_num in range(2):
        c.saveState()
        c.translate(layout.bleed, layout.bleed)
        
        args_v2 = {
            'address': address, 'beds': beds, 'baths': baths, 'sqft': sqft, 'price': price,
            'agent_name': agent_name, 'brokerage': brokerage, 
            'agent_email': agent_email, 'agent_phone': agent_phone,
            'qr_key': None, 'agent_photo_key': agent_photo_key, 'logo_key': agent_logo_key,
            'sign_color': sign_color, 'qr_value': qr_url, 'user_id': user_id,
            'license_number': None, 'state': prop_row.get('state'), 'city': prop_row.get('city')
        }

        if layout_id in ('yard_phone_qr_premium', 'listing_v2_phone_qr_premium'):
             _draw_yard_phone_qr_premium(c, layout, **args_v2)
             
        elif layout_id in ('yard_address_qr_premium', 'listing_v2_address_qr_premium'):
             _draw_yard_address_qr_premium(c, layout, **args_v2)

        elif layout_id == 'yard_modern_round':
            if is_landscape:
                _draw_landscape_split_layout(
                    c, layout, address, beds, baths, sqft, price,
                    agent_name, brokerage, agent_email, agent_phone,
                    None, agent_photo_key, sign_color, qr_value=qr_url, user_id=user_id, logo_key=agent_logo_key
                )
            else:
                _draw_modern_round_layout(
                    c, layout, address, beds, baths, sqft, price,
                    agent_name, brokerage, agent_email, agent_phone,
                    None, agent_photo_key, sign_color, qr_value=qr_url,
                    user_id=user_id, logo_key=agent_logo_key
                )

        else:
            if is_landscape:
                _draw_landscape_split_layout(
                    c, layout, address, beds, baths, sqft, price,
                    agent_name, brokerage, agent_email, agent_phone,
                    None, agent_photo_key, sign_color, qr_value=qr_url, user_id=user_id, logo_key=agent_logo_key
                )
            else:
                _draw_standard_layout(
                    c, layout, address, beds, baths, sqft, price,
                    agent_name, brokerage, agent_email, agent_phone,
                    None, agent_photo_key, sign_color, qr_value=qr_url, user_id=user_id, logo_key=agent_logo_key
                )
        
        c.restoreState()
        c.showPage()
    
    c.save()
    pdf_buffer.seek(0)
    
    # Save to storage
    # ----------------
    # Save to storage
    # ----------------
    if output_key:
        pdf_key = output_key
    else:
        folder = f"pdfs/order_{order_id}" if order_id else "pdfs/misc"
        # Filename: yard_sign_{SIZE}.pdf  (e.g. yard_sign_18x24.pdf)
        # If we have multiple signs? This generator is usually 1-to-1 with an order item.
        pdf_key = f"{folder}/yard_sign_{sign_size}.pdf"
    
    storage.put_file(pdf_buffer, pdf_key, content_type="application/pdf")
    
    return pdf_key


def generate_yard_sign_pdf_from_order_row(order_row, *, storage=None, db=None):
    """
    Wrapper to generate yard sign PDF from a database Order row (dictionary or Row).
    Fetches missing logical relations like Agent, Property if needed.
    
    This is the SINGLE source of truth for yard-sign PDFs, used by:
    - Preview/resize regeneration (routes/orders.py)
    - Fulfillment print generation (services/fulfillment.py)
    
    Args:
        order_row: DB row dict from orders table
        storage: Optional storage instance (will get default if not provided)
        db: Optional db connection (will get default if not provided)
        
    Returns:
        str: Storage key for generated PDF
    """
    # Get defaults if not provided
    if storage is None:
        storage = get_storage()
    if db is None:
        db = get_db()
    
    # Delegate to the main generator
    # generate_yard_sign_pdf already handles dict-like order objects
    return generate_yard_sign_pdf(order_row, output_path=None)
