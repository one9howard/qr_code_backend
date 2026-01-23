from flask import Blueprint, request, jsonify
from services.events import track_event, CLIENT_EVENTS

events_bp = Blueprint('events', __name__)

@events_bp.route('/api/events', methods=['POST'])
def track_client_event():
    """
    Intake for client-side events.
    Enforces restricted allowlist.
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "Invalid JSON"}), 400
        
    event_type = data.get('event_type')
    
    if event_type not in CLIENT_EVENTS:
        return jsonify({"success": False, "error": "Invalid event type"}), 400
        
    # Validation handled by service, but we reject early if wrong source
    # Actually service handles it via source="client" validatio inside standard rules?
    # Service checks Allowlist based on source.
    
    track_event(
        event_type,
        source="client",
        property_id=data.get('property_id'),
        qr_code=data.get('qr_code'),
        payload=data.get('payload')
    )
    
    return jsonify({"success": True})
