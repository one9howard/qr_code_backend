"""
Listing Sign PDF Generator

Generates print-ready PDFs for listing signs.
Always produces 2 pages (front/back) for double-sided printing.
Returns storage key (not local path).
"""
import io
import logging
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from database import get_db
from utils.storage import get_storage
from utils.pdf_generator import LayoutSpec, SIGN_SIZES, DEFAULT_SIGN_SIZE, _draw_standard_layout, _draw_landscape_split_layout, hex_to_rgb
from config import BASE_URL
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
        # Parsing failed, return original cleaned string
        return price_str


def generate_listing_sign_pdf(order, output_path=None):
    """
    Generate the high-res PDF for a Listing Sign.
    Enforces Phase 6 rules: Always Double Sided (2 pages).
    
    Args:
        order: Order dict/row object with order data
        output_path: Deprecated - ignored. Returns storage key.
    
    Returns:
        str: Storage key for generated PDF
    """
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
    
    # Sign config - use order's persisted color and size
    sign_color = get_val(order, 'sign_color') or '#1F6FEB'  # DEFAULT_SIGN_COLOR fallback
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
             raise ValueError(f"Property {prop_row['id']} has no qr_code. Cannot generate valid Listing Sign.")
    
    qr_url = property_scan_url(BASE_URL, qr_code)
    
    # Layout config
    if sign_size not in SIGN_SIZES:
        sign_size = DEFAULT_SIGN_SIZE
    size_config = SIGN_SIZES[sign_size]
    layout = LayoutSpec(size_config['width_in'], size_config['height_in'])
    
    # Generate PDF in memory
    pdf_buffer = io.BytesIO()
    c = canvas.Canvas(pdf_buffer, pagesize=(layout.width + 2*layout.bleed, layout.height + 2*layout.bleed))
    
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
                None, None, sign_color, qr_value=qr_url
            )
        else:
            _draw_standard_layout(
                c, layout, address, beds, baths, sqft, price,
                agent_name, brokerage, agent_email, agent_phone,
                None, None, sign_color, qr_value=qr_url
            )
        
        c.restoreState()
        c.showPage()
    
    c.save()
    pdf_buffer.seek(0)
    
    # Save to storage
    folder = f"pdfs/order_{order_id}"
    pdf_key = f"{folder}/listing_sign_{sign_size}.pdf"
    
    storage.put_file(pdf_buffer, pdf_key, content_type="application/pdf")
    
    return pdf_key
