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

@dev_bp.route("/dev/photos")
def debug_photos():
    db = get_db()
    photos = db.execute("SELECT id, property_id, filename FROM property_photos LIMIT 50").fetchall()
    agents = db.execute("SELECT id, photo_filename, logo_filename FROM agents WHERE photo_filename IS NOT NULL OR logo_filename IS NOT NULL LIMIT 50").fetchall()
    
    return jsonify({
        "property_photos": [dict(p) for p in photos],
    })

@dev_bp.route("/dev/validate-photos")
def validate_photos():
    import os
    from flask import current_app, request
    from database import get_db
    
    db = get_db()
    instance_dir = current_app.instance_path
    
    # Check Property Photos
    photos = db.execute("SELECT id, property_id, filename FROM property_photos").fetchall()
    missing = []
    
    for p in photos:
        file_path = os.path.join(instance_dir, p['filename'])
        if not os.path.exists(file_path):
            missing.append({"id": p['id'], "property_id": p['property_id'], "filename": p['filename'], "path_checked": file_path})

    if request.args.get('delete') == 'true':
        if missing:
            ids = tuple(m['id'] for m in missing)
            db.execute(f"DELETE FROM property_photos WHERE id IN {ids}")
            db.commit()
            return jsonify({"status": "deleted", "count": len(missing), "deleted_ids": ids})
        return jsonify({"status": "no_missing_found"})
            
    return jsonify({
        "total_photos": len(photos),
        "missing_count": len(missing),
        "missing_files": missing,
        "instruction": "Add ?delete=true to URL to remove these records."
    })

