"""Strict validation for Print Product payloads.

Enforces:
- SmartSign payload strictness (fields, lengths, colors)
- Image verification (resolution)
"""
import re
from io import BytesIO
from PIL import Image
from services.print_catalog import (
    SMART_SIGN_LAYOUTS, 
    BANNER_COLOR_PALETTE, 
    validate_sku,
    validate_layout
)
from utils.storage import get_storage

def validate_smartsign_payload(layout_id, payload):
    """
    Validate SmartSign design payload.
    Returns list of error strings. Empty list = valid.
    
    Rules:
    - banner_color_id in palette
    - agent_name required (<= 40)
    - agent_phone required (<= 20)
    - agent_email optional (<= 60, must have @)
    - brokerage_name optional (<= 50)
    - images: if key present, must exist and meet min_res
    """
    errors = []
    
    if layout_id not in SMART_SIGN_LAYOUTS:
        errors.append(f"Invalid layout_id: {layout_id}")

    # 1. Banner Color
    banner_id = payload.get('banner_color_id')
    if not banner_id or banner_id not in BANNER_COLOR_PALETTE:
        errors.append(f"Invalid or missing banner_color_id: {banner_id}")

    # 2. Agent Name
    name = payload.get('agent_name')
    if not name:
        errors.append("agent_name is required")
    elif len(name) > 40:
        errors.append("agent_name exceeds 40 characters")

    # 3. Agent Phone
    phone = payload.get('agent_phone')
    if not phone:
        errors.append("agent_phone is required")
    elif len(phone) > 20:
        errors.append("agent_phone exceeds 20 characters")

    # 4. Agent Email (optional)
    email = payload.get('agent_email')
    if email:
        if len(email) > 60:
            errors.append("agent_email exceeds 60 characters")
        if '@' not in email:
            errors.append("agent_email must be valid email")

    # 5. Brokerage Name (optional)
    brokerage = payload.get('brokerage_name')
    if brokerage and len(brokerage) > 50:
        errors.append("brokerage_name exceeds 50 characters")

    # 6. Image Validation
    storage = get_storage()
    
    # helper for image checking
    def check_image(key_field, min_w, min_h):
        key = payload.get(key_field)
        if key:
            if not storage.exists(key):
                errors.append(f"{key_field} file not found: {key}")
                return

            try:
                # We need to read the file to check dims. 
                # This might be slow for S3, but 'Strict' requirement says verify.
                # Use HEAD info if possible? No, need strict pixel dims.
                # get_file returns BytesIO
                file_obj = storage.get_file(key)
                img = Image.open(file_obj)
                w, h = img.size
                if w < min_w or h < min_h:
                    errors.append(f"{key_field} resolution {w}x{h} too low. Min: {min_w}x{min_h}")
            except Exception as e:
                errors.append(f"Failed to validate {key_field}: {str(e)}")

    check_image('agent_headshot_key', 500, 500)
    check_image('agent_logo_key', 300, 300)

    return errors


def validate_order_print_spec(order):
    """
    Validate print spec on an existing Order object.
    Returns list of error strings.
    """
    errors = []
    
    if not order.print_product:
        # If it's a legacy order, maybe skip? But instructions say 'Strict'.
        # Assuming this is called for NEW print jobs or checkout.
        # If order is already created, we validate what we have.
        return ["Missing print_product"]

    # Validate SKU
    ok, reason = validate_sku(order.print_product, order.material, order.sides)
    if not ok:
        errors.append(f"Invalid SKU: {reason}")
        
    # Validate Layout
    ok, reason = validate_layout(order.print_product, order.layout_id)
    if not ok:
        errors.append(f"Invalid Layout: {reason}")
        
    # Product Specific Validation
    if order.print_product == 'smart_sign':
        if not order.design_payload:
            errors.append("SmartSign requires design_payload")
        else:
            payload_errors = validate_smartsign_payload(order.layout_id, order.design_payload)
            errors.extend(payload_errors)
            
    return errors
