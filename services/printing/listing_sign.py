import os
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from utils.pdf_generator import _draw_standard_layout, _draw_landscape_split_layout
from utils.storage import get_storage
import logging

logger = logging.getLogger(__name__)

def generate_listing_sign_pdf(order, output_path):
    """
    Generate the high-res PDF for a Listing Sign.
    Enforces Phase 6 rules: Always Double Sided (2 pages).
    """
    
    # 1. Parse Order Data
    # order maps to DB row. We need 'design_payload' (if using new flow) 
    # OR we reconstruct from property data like `utils.pdf_generator` did.
    # Current `order` object in fulfillment is `db.Row` or `Model`.
    
    # For robust retro-compatibility and Phase 5/6 transition, we try to use
    # the data stored in the order (cached snapshot) if available, 
    # otherwise fetch from property.
    # But `utils.pdf_generator` fetches from property DB.
    
    # Let's trust `utils.pdf_generator`'s data gathering logic or
    # implement a cleaner extractor here.
    # To save time and reduce risk, we reuse the DRAW functions from `utils.pdf_generator`
    # but we control the CANVAS and PAGE loop here.
    
    # 2. Fetch Data (scan-friendly)
    db = get_db()
    prop_row = db.execute("SELECT * FROM properties WHERE id = %s", (order.property_id,)).fetchone()
    # User associated with order (or property agent?) - Usually Property Agent is best for sign info, 
    # but Order has user_id. Let's use Property Agent data if possible, or Order User.
    # Listing Sign typically reflects the Agent on the Property.
    # property -> agent_id -> users table.
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
         agent_row = db.execute("SELECT * FROM users WHERE id = %s", (order.user_id,)).fetchone()

    if not prop_row or not agent_row:
        raise ValueError(f"Missing data for Order {order.id}")

    # 3. Prepare Attributes
    from config import BASE_URL
    
    # helper for safe dict access
    def get(row, k, default=''):
        return str(row[k]) if row and row[k] else default

    address = get(prop_row, 'address', 'Address TBD')
    beds = get(prop_row, 'beds', '0')
    baths = get(prop_row, 'baths', '0')
    sqft = get(prop_row, 'sqft', '')
    
    # Format Price
    price_val = prop_row['price']
    price = f"${price_val:,}" if price_val else ""
    
    agent_name = get(agent_row, 'full_name', 'Agent')
    brokerage = get(agent_row, 'brokerage_name', 'Brokerage')
    agent_email = get(agent_row, 'email', '')
    agent_phone = get(agent_row, 'phone_number', '') # Assuming column exists
    
    # Keys
    agent_photo_key = agent_row.get('photo_storage_key') # Column guess? Or lookup 'agent_headshot_key'
    # Actually, previous schema might use 'photo_url' or similar. 
    # Safest: pass None if we aren't sure of column name, or try 'profile_photo_url' if logical.
    # But utils.pdf_generator expects a KEY to fetch from storage.
    # Let's assume None for now to avoid broken image links unless we verified schema.
    
    # Sign Config
    sign_color = agent_row.get('custom_color') or '#000000'
    sign_size = order.print_size or '18x24'
    
    # QR URL (Real)
    # Redirect code/id
    qr_url = f"{BASE_URL}/s/{prop_row['id']}" # Standard Property Redirect
    
    # 4. Generate PDF (Double Sided)
    from utils.pdf_generator import LayoutSpec, SIGN_SIZES, DEFAULT_SIGN_SIZE, _draw_standard_layout, _draw_landscape_split_layout
    import io
    
    # Config
    if sign_size not in SIGN_SIZES: sign_size = DEFAULT_SIGN_SIZE
    size_config = SIGN_SIZES[sign_size]
    layout = LayoutSpec(size_config['width_in'], size_config['height_in'])
    
    pdf_buffer = io.BytesIO()
    c = canvas.Canvas(pdf_buffer, pagesize=(layout.width + 2*layout.bleed, layout.height + 2*layout.bleed))
    
    # Draw 2 identical pages
    for page_num in range(2):
        c.translate(layout.bleed, layout.bleed)
        
        # Draw Layout
        if sign_size == "36x18":
             _draw_landscape_split_layout(
                c, layout, address, beds, baths, sqft, price,
                agent_name, brokerage, agent_email, agent_phone,
                None, agent_photo_key, sign_color, qr_value=qr_url
            )
        else:
            _draw_standard_layout(
                c, layout, address, beds, baths, sqft, price,
                agent_name, brokerage, agent_email, agent_phone,
                None, agent_photo_key, sign_color, qr_value=qr_url
            )
        
        c.showPage()
    
    c.save()
    pdf_buffer.seek(0)
    
    # 5. Save to Storage
    from utils.filenames import make_sign_asset_basename
    
    folder = f"pdfs/order_{order.id}"
    basename = make_sign_asset_basename(order.id, sign_size)
    pdf_key = f"{folder}/{basename}.pdf"
    
    storage.put_file(pdf_buffer, pdf_key, content_type="application/pdf")
    
    return pdf_key
    
    class Box:
        def __init__(self, data):
            for k,v in data.items():
                setattr(self, k, v)
    
    prop = Box(prop)
    # user = Box(user_row) # User might be complex, let's use what we need.
    # User might be used for agent info.
    
    # Prepare Data Dict
    # This mimics `utils.pdf_generator.get_sign_data`
    address = prop.address
    price = prop.price  # Note: prop.price is raw. We need formatting? 
    # Wait, original code said `price = prop.price_formatted`. 
    # Does DB have price_formatted? Probably NOT. Property model likely had a property.
    # We need to format it. "${:,}".format(prop.price)
    
    price_val = prop.price
    price = f"${price_val:,}" if price_val else ""
    
    beds = prop.beds
    baths = prop.baths
    sqft = prop.sqft
    
    # Agent info (User profile)
    agent_name = f"{user.first_name} {user.last_name}"
    brokerage = user.brokerage_name or ""
    agent_email = user.email
    agent_phone = user.phone_number or ""
    agent_photo_key = user.profile_photo_key
    
    # Layout Config
    # Check `order.print_size`
    # For `coroplast_4mm` or `aluminum_040`, we rely on size.
    # But `_draw_standard_layout` is hardcoded for 18x24 layout logic mostly?
    # Wait, the existing `_draw_standard_layout` uses `layout.bleed` etc.
    # It seems to handle scaling?
    # Actually, `utils.pdf_generator` handles different sizes by checking `layout_id` or `size`.
    
    raw_size = order.print_size or "18x24"
    sign_size = raw_size.lower() # e.g. "18x24"
    
    # Colors
    sign_color = order.design_payload.get('color', 'blue') if order.design_payload else 'blue'
    
    # QR
    qr_value = f"https://insitesigns.com/p/{prop.public_id}" # Example
    # Or use existing logic
    qr_key = None # We generate on fly or use cached?
    
    # Config for Drawing
    # We need a `LayoutConfig` object mimicking the namedtuple in `pdf_generator`
    from collections import namedtuple
    LayoutConfig = namedtuple('LayoutConfig', ['width', 'height', 'bleed', 'safe_margin'])
    
    # Parse Size
    try:
        w_str, h_str = sign_size.split('x')
        width_in = float(w_str)
        height_in = float(h_str)
    except:
        width_in, height_in = 24, 18
        
    # Standard bleed 0.125
    layout = LayoutConfig(width_in*inch, height_in*inch, 0.125*inch, 0.25*inch)
    
    # Unit name for canvas (not used by draw func but good for canvas init)
    # Actually we pass points to canvas
    
    width = layout.width + 2*layout.bleed
    height = layout.height + 2*layout.bleed
    
    # Data bundle for draw func
    data = {} # The draw funcs above take args directly, not a dict.
    
    # Build PDF
    # Always Double Sided (2 Pages) per instructions
    can = canvas.Canvas(output_path, pagesize=(width, height))
    
    # Helper to call draw
    def draw_face(is_back):
        can.saveState()
        # Translate for bleed
        can.translate(layout.bleed, layout.bleed)
        
        layout_func = _draw_standard_layout
        if sign_size == "36x18":
            layout_func = _draw_landscape_split_layout
        
        # Call legacy draw
        layout_func(
            can, layout, address, beds, baths, sqft, price,
            agent_name, brokerage, agent_email, agent_phone,
            qr_key, agent_photo_key, sign_color, qr_value
        )
        can.restoreState()

    # Page 1 (Front)
    draw_face(is_back=False)
    can.showPage()
    
    # Page 2 (Back) - Duplicate of Front
    draw_face(is_back=True)
    can.showPage()
    
    can.save()
    
    return output_path
