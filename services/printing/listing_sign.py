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
    
    # We need to gather the `data` dict expected by `_draw_standard_layout`.
    # We need to gather the `data` dict expected by `_draw_standard_layout`.
    from database import get_db
    from models import User
    from utils.qr import generate_qr_code_url
    
    # Fetch related
    prop_id = order.property_id
    user_id = order.user_id
    
    db = get_db()
    
    # Re-fetch full objects via SQL
    prop = db.execute("SELECT * FROM properties WHERE id = %s", (prop_id,)).fetchone()
    # User can be fetched via User model which supports get_by or raw sql
    user_row = db.execute("SELECT * FROM users WHERE id = %s", (user_id,)).fetchone()
    
    if not prop or not user_row:
        raise ValueError("Property or User not found for order")

    # Map to expected object interface (dot notation or dict access)
    # prop is a RealDictRow usually, so prop['address'] works. 
    # But existing code below might use dot notation: prop.address.
    # Let's wrap explicitly or change downstream usage.
    # checking downstream usage... "address = prop.address"
    # So we need an object or change downstream to use dict access.
    # Let's change downstream to use dict access OR Wraps. 
    # Simplest: use a dict access below or a simple class.
    # Actually, let's just update the extraction below.
    
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
