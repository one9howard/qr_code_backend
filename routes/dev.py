from flask import Blueprint, jsonify
from flask_login import login_required, current_user
from database import get_db

dev_bp = Blueprint('dev', __name__)

@dev_bp.route("/dev/user-status")
@login_required
def user_status():
    db = get_db()
    # Fetch fresh from DB to be sure
    user_row = db.execute("SELECT * FROM users WHERE id = %s", (current_user.id,)).fetchone()
    
    return jsonify({
        "session_user": {
            "id": current_user.id,
            "subscription_status": current_user.subscription_status,
            "subscription_end_date": current_user.subscription_end_date,
            "stripe_customer_id": current_user.stripe_customer_id
        },
        "db_user": dict(user_row) if user_row else None
    })
