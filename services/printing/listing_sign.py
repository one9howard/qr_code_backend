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

logger = logging.getLogger(__name__)


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
    
    # Fetch agent data
    agent_row = None
    if prop_row['agent_id']:
        agent_row = db.execute("""
            SELECT u.*, a.brokerage_name, a.custom_color 
            FROM agents a 
            JOIN users u ON a.user_id = u.id 
            WHERE a.id = %s
        """, (prop_row['agent_id'],)).fetchone()
    
    if not agent_row:
        # Fallback to order user
        agent_row = db.execute(
            "SELECT * FROM users WHERE id = %s", (user_id,)
        ).fetchone()

    if not prop_row or not agent_row:
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
    price = f"${int(price_val):,}" if price_val else ""
    
    agent_name = get(agent_row, 'full_name', 'Agent')
    brokerage = get(agent_row, 'brokerage_name', '')
    agent_email = get(agent_row, 'email', '')
    agent_phone = get(agent_row, 'phone_number', '')
    
    # Sign config
    sign_color = agent_row.get('custom_color') or '#000000'
    sign_size = get_val(order, 'print_size') or '18x24'
    
    # QR URL
    qr_url = f"{BASE_URL}/s/{prop_row['id']}"
    
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
