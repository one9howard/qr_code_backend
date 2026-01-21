"""Listing Sign Generator Service

Reuses existing layout logic from utils/pdf_generator but adds:
- Double-sided support (duplication)
- Database/Order integration
"""
import io
from reportlab.pdfgen import canvas
from database import get_db
from utils.pdf_generator import (
    LayoutSpec, 
    _draw_standard_layout, 
    _draw_landscape_split_layout, 
    SIGN_SIZES, 
    DEFAULT_SIGN_SIZE,
    DEFAULT_SIGN_COLOR
)
from utils.storage import get_storage
from utils.filenames import make_sign_asset_basename

def generate_listing_sign_pdf(db, order):
    """
    Generate PDF for a listing sign order.
    
    Args:
        db: Database connection
        order: Order row/dict
        
    Returns:
        bytes: PDF content bytes
    """
    # 1. Fetch Property Data
    # Listing signs usually linked to a property via something? 
    # Current orders table has 'property_id' or similar?
    # Actually, listing_sign orders come from 'order-sign' route which takes form data.
    # The order record might have a 'meta_json' or columns. 
    # Let's check how fulfillment currently gets address etc.
    # update: fulfillment.py for 'sign' order doesn't seem to regenerate PDF usually? 
    # It takes PDF from 'sign_pdf_path'.
    # BUT Phase 5 C1 says: "generate_listing_sign_pdf(db, order) -> bytes... Must load order + property + agent info"
    # This implies we are generating it FRESH from data, not reading a pre-stored file.
    
    # However, existing orders table might not have all fields if they were transient in the form.
    # But wait, 'listing_sign' usually implies the "Sign Listing" product. 
    # Let's assume the order holds a reference to property_id or has the data snapshotted in meta_json.
    # routes/orders.py saves: shipping_address, but maybe not sign details if they were just used to generate the PDF?
    # Wait, routes/agent.py (Listing Kit?) saves the order.
    # If the user buys a sign, we must have the data.
    # Current flow: User fills form -> `generate_pdf_sign` called -> `pdf_key` stored in order.
    
    # New flow Requirement: "generate_listing_sign_pdf(db, order) -> bytes"
    # This suggests we need to be able to regenerate it.
    # If the order stores 'property_id', we can fetch property data. 
    # If it stores 'meta_json' with overrides, we key off that.
    
    # Let's look at order schema/provenance.
    # If I cannot rely on Property ID, I might need to rely on the *existing* PDF if we can't regenerate?
    # But C1 "Must support sides... double = render front + back".
    # If the stored PDF is single page (legacy), and we need double, we'd need to manipulate the PDF.
    # OR, we assume we can re-render.
    
    # Checking `routes/orders.py` order creation...
    # It likely saves `sign_pdf_path`.
    # Phase 5 E1 says: "Listing sign checkout... Set on order: layout_id... design_payload optional".
    # Maybe we are moving to storing the data TO generate, instead of the generated PDF?
    # Yes, "Data model changes... design_payload JSONB".
    # So we should use design_payload.
    
    payload = order.get('design_payload') or {}
    
    # We also need property info if it's a listing sign.
    # If payload is empty, maybe fallback to property?
    # Let's assume payload contains the snapshot or we fetch from property.
    
    # For now, I'll attempt to use payload fields, falling back to property_id lookup.
    
    prop = None
    if order.get('property_id'):
        prop = db.execute("SELECT * FROM properties WHERE id = %s", (order['property_id'],)).fetchone()
        
    # Helper to get field from payload OR property OR order overrides
    def get_val(key, prop_col=None, default=''):
        val = payload.get(key)
        if val: return val
        # Legacy/Flat columns on order?
        if key in order and order[key]: return order[key]
        # Property
        if prop and prop_col:
            return prop[prop_col] or ''
        return default

    # Extract Data
    address = get_val('address', 'address')
    beds = get_val('beds', 'beds', '0')
    baths = get_val('baths', 'baths', '0')
    sqft = get_val('sqft', 'sqft', '')
    price = get_val('price', 'price', '')
    
    agent_name = get_val('agent_name') # Need agent info. Order -> User?
    brokerage = get_val('brokerage')
    agent_email = get_val('agent_email')
    agent_phone = get_val('agent_phone')
    
    # If agent info missing from payload, fetch from user?
    if not agent_name and order.get('user_id'):
        user = db.execute("SELECT * FROM users WHERE id = %s", (order['user_id'],)).fetchone()
        if user:
            agent_name = user['name']
            brokerage = user.get('brokerage_name', '')
            agent_email = user['email']
            agent_phone = user.get('phone', '')

    # QR/Photos
    qr_key = get_val('qr_key')
    agent_photo_key = get_val('agent_photo_key')
    
    # Legacy fallbacks if stored in non-standard cols? (unlikely for new flow)
    
    # Config
    sign_color = get_val('sign_color', default=DEFAULT_SIGN_COLOR)
    # Mapping old 'sign_size' if present
    sign_size = get_val('sign_size', default=DEFAULT_SIGN_SIZE)
    if 'sign_size' in order and order['sign_size']:
        sign_size = order['sign_size']
        
    # --- Generation ---
    size_config = SIGN_SIZES.get(sign_size, SIGN_SIZES[DEFAULT_SIGN_SIZE])
    layout = LayoutSpec(size_config['width_in'], size_config['height_in'])
    
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=(layout.width + 2*layout.bleed, layout.height + 2*layout.bleed))
    
    sides = order.get('sides', 'single')
    is_double = (sides == 'double')
    
    # Draw Front
    c.translate(layout.bleed, layout.bleed)
    
    # Call existing layout logic
    # Reuse _draw_landscape_split_layout or _draw_standard_layout
    layout_func = _draw_standard_layout
    if sign_size == "36x18":
        layout_func = _draw_landscape_split_layout
        
    layout_func(
        c, layout, address, beds, baths, sqft, price,
        agent_name, brokerage, agent_email, agent_phone,
        qr_key, agent_photo_key, sign_color
    )
    
    c.showPage()
    
    if is_double:
        # Draw Back (Duplicate of front)
        c.translate(layout.bleed, layout.bleed) # Reset translation for new page
        layout_func(
            c, layout, address, beds, baths, sqft, price,
            agent_name, brokerage, agent_email, agent_phone,
            qr_key, agent_photo_key, sign_color
        )
        c.showPage()
        
    c.save()
    buffer.seek(0)
    return buffer.read()
