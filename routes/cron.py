from flask import Blueprint, request, jsonify
import os
from services.cleanup import cleanup_expired_properties

cron_bp = Blueprint("cron", __name__, url_prefix="/cron")

@cron_bp.route("/cleanup-expired", methods=["POST"])
def cleanup_expired():
    expected_token = os.environ.get("CRON_TOKEN")
    if not expected_token:
        # If env var not set, we can't verify, so deny.
        return jsonify({"success": False, "error": "unauthorized"}), 401
        
    incoming_token = request.headers.get("X-CRON-TOKEN")
    if incoming_token != expected_token:
        return jsonify({"success": False, "error": "unauthorized"}), 401
        
    try:
        count = cleanup_expired_properties()
        return jsonify({"success": True, "deleted": count})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
