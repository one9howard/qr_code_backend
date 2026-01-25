from flask import abort, request
from flask_login import current_user
from models import Order

def get_order_for_request(order_id):
    """
    Centralized logic to retrieve an order and authorize access.
    
    Rules:
    1. If user is authenticated: Allow if order.user_id matches current_user.id (or admin).
    2. If user is guest: Allow if request header/param guest_token matches order.guest_token.
    
    Returns: order (Order object)
    Raises: 403 if unauthorized, 404 if not found.
    """
    order = Order.get(order_id)
    if not order:
        abort(404)
        
    authorized = False
    
    # Check Authenticated User
    if current_user.is_authenticated:
        if current_user.id == order.user_id or getattr(current_user, 'is_admin', False):
            authorized = True
            
    # Check Guest Token if not already authorized
    if not authorized:
        # Check both JSON body (for POST) and query args (for GET) and Headers
        req_token = None
        
        # 1. Check Query Params
        req_token = request.args.get('guest_token')
        
        # 2. Check JSON Body
        if not req_token and request.is_json:
            req_token = request.json.get('guest_token')
            
        # 3. Check Headers
        if not req_token:
            req_token = request.headers.get('X-Guest-Token')
            
        if req_token and order.guest_token and req_token == order.guest_token:
            authorized = True
            
    if not authorized:
        abort(403)
        
    return order
