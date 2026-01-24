
from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from services.branding import save_qr_logo, set_use_qr_logo, delete_qr_logo
from services.subscriptions import is_subscription_active

branding_bp = Blueprint('branding', __name__)

@branding_bp.route('/api/branding/qr-logo', methods=['POST'])
@login_required
def upload_qr_logo():
    """
    Upload a new QR logo.
    PRO ONLY.
    """
    # 1. Check Pro
    if not is_subscription_active(current_user.subscription_status):
        return jsonify({"ok": False, "error": "pro_required"}), 403
        
    # 2. Check File
    if 'logo' not in request.files:
        return jsonify({"ok": False, "error": "No file part"}), 400
        
    file = request.files['logo']
    if file.filename == '':
        return jsonify({"ok": False, "error": "No selected file"}), 400
        
    try:
        # 3. Save
        result = save_qr_logo(current_user.id, file)
        
        # Auto-enable on successful upload? Plan doesn't rigidly specify, but nice UX.
        # User requested: "Enabling ... is Pro-only". 
        # Explicit toggle endpoint exists. Let's NOT auto-enable to be safe/consistent with "default OFF".
        
        return jsonify({"ok": True})
        
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:
        current_app.logger.error(f"Logo upload failed: {e}")
        return jsonify({"ok": False, "error": "Internal server error"}), 500


@branding_bp.route('/api/branding/qr-logo/toggle', methods=['POST'])
@login_required
def toggle_qr_logo():
    """
    Enable/Disable QR logo usage.
    Enable: PRO ONLY.
    Disable: ANYONE.
    """
    data = request.get_json()
    if not data or 'use_qr_logo' not in data:
        return jsonify({"ok": False, "error": "Missing use_qr_logo"}), 400
        
    enabled = bool(data['use_qr_logo'])
    
    if enabled:
        # Pro Check
        if not is_subscription_active(current_user.subscription_status):
             return jsonify({"ok": False, "error": "pro_required"}), 403
    
    set_use_qr_logo(current_user.id, enabled)
    return jsonify({"ok": True, "use_qr_logo": enabled})


@branding_bp.route('/api/branding/qr-logo', methods=['DELETE'])
@login_required
def delete_qr_logo_route():
    """
    Delete QR logo assets and disable toggle.
    ANYONE allowed (cleanup).
    """
    delete_qr_logo(current_user.id)
    return jsonify({"ok": True})
