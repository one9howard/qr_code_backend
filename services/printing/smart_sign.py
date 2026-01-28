"""
Unified SmartSign PDF Generator (Wrapper).

Routes all requests to the single source of truth: services/pdf_smartsign.py
This file replaces the legacy generator entirely.
"""
import logging
from services.pdf_smartsign import generate_smartsign_pdf

logger = logging.getLogger(__name__)

def generate_smart_sign_pdf(order, output_path=None):
    """
    Generate SmartSign PDF (Unified Dispatch).
    
    Args:
        order: Order dict/row object with 'design_payload' and 'id'.
        output_path: Ignored (legacy argument).
    
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
        
        # Legacy fallback keys
        if not print_size: print_size = order.get('size')
    else:
        # Row / Object
        payload = getattr(order, 'design_payload', {}) or {}
        order_id = getattr(order, 'id', None)
        user_id = getattr(order, 'user_id', None)
        print_size = getattr(order, 'print_size', None)
        layout_id = getattr(order, 'layout_id', None)

    # 2. Construct Mock Asset for Generator
    asset_data = payload.copy()
    
    # Ensure critical fields overwrite payload if present in order root
    if print_size: asset_data['print_size'] = print_size
    if layout_id: asset_data['layout_id'] = layout_id
    
    # Check for legacy keys in payload if new ones missing
    if 'agent_name' in asset_data and 'brand_name' not in asset_data:
        asset_data['brand_name'] = asset_data['agent_name']
    
    return generate_smartsign_pdf(asset_data, order_id=order_id, user_id=user_id)
