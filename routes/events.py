from flask import Blueprint, request, jsonify
from services.events import track_event, CLIENT_EVENTS
from extensions import limiter

events_bp = Blueprint('events', __name__)

@events_bp.route('/api/events', methods=['POST'])
@limiter.limit("60/minute") # Protect against flooding
def track_client_event():
    """
    Intake for client-side events.
    Enforces restricted allowlist.
    
    Accepts either:
    - event_type (canonical) or event (alias)
    - payload (canonical) or remaining keys auto-built into payload
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "Invalid JSON"}), 400
    
    # Accept 'event' as alias for 'event_type'
    event_type = data.get('event_type') or data.get('event')
    
    if not event_type:
        return jsonify({"success": False, "error": "Missing event_type"}), 400
        
    if event_type not in CLIENT_EVENTS:
        return jsonify({"success": False, "error": "Invalid event type"}), 400
    
    # Build payload: use explicit payload or auto-build from remaining keys
    payload = data.get('payload')
    if payload is None:
        # Auto-build payload from remaining keys (excluding reserved)
        reserved_keys = {'event_type', 'event', 'property_id', 'qr_code', 'payload'}
        payload = {k: v for k, v in data.items() if k not in reserved_keys}
    
    track_event(
        event_type,
        source="client",
        property_id=data.get('property_id'),
        qr_code=data.get('qr_code'),
        payload=payload
    )
    
    return jsonify({"success": True})

