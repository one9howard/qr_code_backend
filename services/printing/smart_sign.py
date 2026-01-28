"""
Unified SmartSign PDF Generator (Wrapper).

Routes all requests to the single source of truth: services/pdf_smartsign.py
"""
import logging
from services.pdf_smartsign import generate_smartsign_pdf

logger = logging.getLogger(__name__)

def generate_smart_sign_pdf(order, output_path=None):
    """
    Generate SmartSign PDF (Unified Dispatch).
    
    Args:
        order: Order dict/row object with 'design_payload' and 'id'.
        output_path: Ignored.
    
    Returns:
        str: Storage key for generated PDF.
    """
    # 1. Normalize Order Data to Asset-like dict
    if hasattr(order, 'get'):
        # Dict
        payload = order.get('design_payload') or {}
        order_id = order.get('id')
        user_id = order.get('user_id')
        print_size = order.get('print_size')
        layout_id = order.get('layout_id')
    else:
        # Row / Object
        payload = getattr(order, 'design_payload', {}) or {}
        order_id = getattr(order, 'id', None)
        user_id = getattr(order, 'user_id', None)
        print_size = getattr(order, 'print_size', None)
        layout_id = getattr(order, 'layout_id', None)

    # 2. Construct Mock Asset for Generator
    # The generator uses _read() so a flat dict works best
    
    # Extract code from payload if present (Option B Strict), or fallback?
    # For printed orders, the code should be in the payload or retrieved from asset.
    # If sign_asset_id is present, the generator might fetch it? 
    # generate_smartsign_pdf takes 'asset'.
    
    # If we have an order, we might not have a full sign_asset row if it was just created in strictly Option B mode
    # and we are generating for preview (wait, preview uses direct generate_smartsign_pdf).
    # This function is used by PRINT WORKER (fulfillment).
    # Fulfillment happens AFTER webhook, so Asset should exist if it was created in webhook.
    # But wait, create_smart_order logic (modified) won't create asset until webhook.
    # So if we are fulfilling, the asset MUST exist (webhook created it).
    
    # However, to be safe and strictly unified, we should fetch the real asset if possible,
    # or construct a comprehensive dict.
    
    # If order has sign_asset_id, let's try to pass that?
    # generate_smartsign_pdf(asset, ...)
    
    # If the caller is passing 'order', let's check if we can get the asset data.
    # Since generate_smartsign_pdf expects an asset-like object primarily for 'code', 'brand_name', etc.
    # we can construct it from payload + logic.
    
    mock_asset = payload.copy()
    
    # Ensure critical fields
    if print_size: mock_asset['print_size'] = print_size
    if layout_id: mock_asset['layout_id'] = layout_id
    
    # Code:
    # If mock_asset doesn't have 'code', we have a problem.
    # But payload usually won't have 'code' in the old logic?
    # In strictly Option B, we store 'code' in payload.
    # So it should be there.
    
    # If not in payload, check if we can fetch from DB?
    # The print worker usually passes the full order row.
    
    return generate_smartsign_pdf(mock_asset, order_id=order_id, user_id=user_id)

import io
import logging
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.lib import colors
from database import get_db
from utils.storage import get_storage
from collections import namedtuple

logger = logging.getLogger(__name__)

# Context for layout functions
SmartContext = namedtuple('SmartContext', ['width', 'height', 'bleed', 'safe_margin', 'storage'])


def generate_smart_sign_pdf(order, output_path=None):
    """
    Generate SmartSign PDF.
    Rule: Always 2 Pages (Double Sided).
    
    Args:
        order: Order dict/row object with order data
        output_path: Deprecated - ignored. Returns storage key.
    
    Returns:
        str: Storage key for generated PDF
    """
    storage = get_storage()
    
    # Handle both dict-like and object-like access
    def get_val(obj, key, default=None):
        if hasattr(obj, 'get'):
            return obj.get(key, default)
        return getattr(obj, key, default)
    
    order_id = get_val(order, 'id')
    payload = get_val(order, 'design_payload') or {}
    print_size = get_val(order, 'print_size') or "18x24"
    layout_id = get_val(order, 'layout_id')
    
    # Parse JSON if needed
    if isinstance(payload, str):
        import json
        payload = json.loads(payload)
    
    # Parse Size
    try:
        w_str, h_str = print_size.lower().split('x')
        width_in = float(w_str)
        height_in = float(h_str)
    except:
        width_in = 18.0
        height_in = 24.0

    bleed = 0.125 * inch
    width = width_in * inch
    height = height_in * inch
    
    full_width = width + 2*bleed
    full_height = height + 2*bleed
    
    ctx = SmartContext(width, height, bleed, 0.25*inch, storage)
    
    # Select layout function
    layout_func = _draw_minimal
    if layout_id == 'smart_v1_photo_banner':
        layout_func = _draw_photo_banner
    elif layout_id == 'smart_v1_agent_brand':
        layout_func = _draw_agent_brand
    
    # Generate PDF in memory
    pdf_buffer = io.BytesIO()
    c = canvas.Canvas(pdf_buffer, pagesize=(full_width, full_height))
    
    def draw_page():
        c.saveState()
        c.translate(bleed, bleed)
        layout_func(c, ctx, payload, order)
        c.restoreState()

    # Page 1
    draw_page()
    c.showPage()
    
    # Page 2 (Duplicate)
    draw_page()
    c.showPage()
    
    c.save()
    pdf_buffer.seek(0)
    
    # Save to storage
    folder = f"pdfs/order_{order_id}"
    pdf_key = f"{folder}/smart_sign_{print_size}.pdf"
    
    storage.put_file(pdf_buffer, pdf_key, content_type="application/pdf")
    
    return pdf_key


# --- Layout Implementations ---

def _draw_minimal(c: canvas.Canvas, ctx: SmartContext, payload: dict, order):
    """Minimal Layout: Solid Color, QR Code, Name/Phone."""
    color_map = {
        'blue': '#0077ff', 'navy': '#0f172a', 'black': '#000000', 
        'white': '#ffffff', 'red': '#ef4444', 'green': '#22c55e'
    }
    color_id = payload.get('banner_color_id', 'blue')
    hex_bg = color_map.get(color_id, '#0077ff')
    
    # Background
    c.setFillColorRGB(*hex_to_rgb(hex_bg))
    c.rect(-ctx.bleed, -ctx.bleed, ctx.width + 2*ctx.bleed, ctx.height + 2*ctx.bleed, fill=1, stroke=0)
    
    # QR Code
    from utils.pdf_generator import draw_qr
    from config import BASE_URL
    
    qr_url = f"{BASE_URL}"
    asset_id = payload.get('sign_asset_id')
    
    if asset_id:
        db = get_db()
        asset = db.execute("SELECT code FROM sign_assets WHERE id = %s", (asset_id,)).fetchone()
        if asset:
            qr_url = f"{BASE_URL}/r/{asset['code']}"

    qr_size = 8 * inch
    qr_x = (ctx.width - qr_size) / 2
    qr_y = (ctx.height - qr_size) / 2 + 2*inch
    
    # White box for QR
    c.setFillColorRGB(1,1,1)
    c.rect(qr_x - 0.25*inch, qr_y - 0.25*inch, qr_size + 0.5*inch, qr_size + 0.5*inch, fill=1, stroke=0)
    
    # Extract user_id from order
    # Helper to get val is in generate function, but 'order' passed here is the row/dict
    user_id = None
    if isinstance(order, dict):
        user_id = order.get('user_id')
    elif hasattr(order, 'user_id'):
        user_id = order.user_id
    elif hasattr(order, '__getitem__'): # Row
        try:
            user_id = order['user_id']
        except:
            pass

    draw_qr(c, qr_url, x=qr_x, y=qr_y, size=qr_size, user_id=user_id)

    # Agent Info
    c.setFillColorRGB(1,1,1)
    c.setFont("Helvetica-Bold", 48)
    name = payload.get('agent_name', "Agent Name")
    c.drawCentredString(ctx.width/2, 4*inch, name)
    
    c.setFont("Helvetica", 36)
    phone = payload.get('agent_phone', "555-555-5555")
    c.drawCentredString(ctx.width/2, 3*inch, phone)


def _draw_photo_banner(c, ctx, payload, order):
    """Photo Layout."""
    _draw_minimal(c, ctx, payload, order)


def _draw_agent_brand(c, ctx, payload, order):
    """Brand Layout."""
    _draw_minimal(c, ctx, payload, order)


# --- Helpers ---
def hex_to_rgb(hex_str):
    value = hex_str.lstrip('#')
    lv = len(value)
    return tuple(int(value[i:i + lv // 3], 16)/255.0 for i in range(0, lv, lv // 3))
