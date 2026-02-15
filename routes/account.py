import re
from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user, login_user
from werkzeug.security import generate_password_hash, check_password_hash

from database import get_db
from models import User
from config import AGENT_PHOTOS_KEY_PREFIX
from utils.uploads import save_image_upload
from utils.agent_identity import normalize_agent_email, get_agent_by_normalized_email, claim_agent_for_verified_user

account_bp = Blueprint("account", __name__)

@account_bp.route("/account", methods=["GET", "POST"])
@login_required
def index():
    db = get_db()
    
    # Fetch current agent data
    agent = db.execute(
        "SELECT * FROM agents WHERE user_id = %s", 
        (current_user.id,)
    ).fetchone()

    if request.method == "POST":
        action = request.form.get("action")
        
        if action == "update_profile":
            return _handle_profile_update(db, agent)
        elif action == "update_security":
            return _handle_security_update(db)
        else:
            flash("Unknown action.", "error")
            return redirect(url_for("account.index"))

    return render_template("account.html", agent=agent)

from utils.urls import normalize_https_url

def _handle_profile_update(db, agent):
    name = request.form.get("name", "").strip()
    phone = request.form.get("phone", "").strip()
    brokerage = request.form.get("brokerage", "").strip()
    raw_scheduling_url = request.form.get("scheduling_url", "")
    
    if not name:
        flash("Name is required.", "error")
        return redirect(url_for("account.index"))

    # Validate Scheduling URL
    scheduling_url = normalize_https_url(raw_scheduling_url)
    if raw_scheduling_url and not scheduling_url:
        flash("Invalid scheduling link. Must be a valid HTTPS URL (e.g. https://calendly.com/...)", "error")
        return redirect(url_for("account.index"))

    # Handle Photo Upload
    photo_key = None
    if agent:
        photo_key = agent['photo_filename'] # Default to existing

    if "photo" in request.files:
        file = request.files["photo"]
        if file and file.filename != "":
            try:
                base_name = f"agent_{current_user.id}_photo"
                photo_key = save_image_upload(
                    file,
                    AGENT_PHOTOS_KEY_PREFIX,
                    base_name,
                    validate_image=True
                )
            except ValueError as e:
                flash(f"Photo upload error: {str(e)}", "error")
                return redirect(url_for("account.index"))

    try:
        if agent:
            db.execute(
                """
                UPDATE agents 
                SET name = %s, phone = %s, brokerage = %s, photo_filename = %s, scheduling_url = %s
                WHERE id = %s
                """,
                (name, phone, brokerage, photo_key, scheduling_url, agent['id'])
            )
        else:
            email_norm = normalize_agent_email(current_user.email)
            if bool(getattr(current_user, "is_verified", False)):
                claim = claim_agent_for_verified_user(
                    db,
                    current_user.id,
                    email_norm,
                    default_name=name,
                )
                db.execute(
                    """
                    UPDATE agents
                    SET name = %s, phone = %s, brokerage = %s, photo_filename = %s, scheduling_url = %s, email = %s
                    WHERE id = %s
                    """,
                    (name, phone, brokerage, photo_key, scheduling_url, email_norm, claim["agent_id"]),
                )
            else:
                existing = get_agent_by_normalized_email(db, email_norm)
                if existing and existing["user_id"] is not None and int(existing["user_id"]) != int(current_user.id):
                    raise PermissionError("This agent email is already claimed by another account.")
                if existing:
                    db.execute(
                        """
                        UPDATE agents
                        SET name = %s, phone = %s, brokerage = %s, photo_filename = %s, scheduling_url = %s, email = %s
                        WHERE id = %s
                        """,
                        (name, phone, brokerage, photo_key, scheduling_url, email_norm, existing["id"]),
                    )
                else:
                    db.execute(
                        """
                        INSERT INTO agents (user_id, email, name, phone, brokerage, photo_filename, scheduling_url)
                        VALUES (NULL, %s, %s, %s, %s, %s, NULL)
                        """,
                        (email_norm, name, phone, brokerage, photo_key),
                    )
        
        db.commit()
        flash("Profile updated successfully.", "success")
    except Exception as e:
        flash(f"Error updating profile: {str(e)}", "error")
        
    return redirect(url_for("account.index"))

def _handle_security_update(db):
    new_email = request.form.get("email", "").strip().lower()
    current_password = request.form.get("current_password")
    new_password = request.form.get("new_password")
    confirm_password = request.form.get("confirm_password")

    # 1. Update Email
    if new_email and new_email != current_user.email:
        # Check uniqueness
        exists = db.execute("SELECT 1 FROM users WHERE email = %s", (new_email,)).fetchone()
        if exists:
            flash("That email is already in use.", "error")
            return redirect(url_for("account.index"))
        
        try:
            db.execute("UPDATE users SET email = %s WHERE id = %s", (new_email, current_user.id))
            # Also update agent email to keep in sync
            db.execute("UPDATE agents SET email = %s WHERE user_id = %s", (new_email, current_user.id))
            db.commit()
            
            # Update session user
            current_user.email = new_email
            flash("Email updated.", "success")
        except Exception as e:
            flash(f"Error updating email: {str(e)}", "error")
            return redirect(url_for("account.index"))

    # 2. Update Password
    if new_password:
        if not current_password:
            flash("Current password required to change password.", "error")
            return redirect(url_for("account.index"))
            
        # Verify current - we need the password hash
        user_row = db.execute("SELECT password_hash FROM users WHERE id = %s", (current_user.id,)).fetchone()
        if not user_row or not check_password_hash(user_row['password_hash'], current_password):
            flash("Incorrect current password.", "error")
            return redirect(url_for("account.index"))
            
        if new_password != confirm_password:
            flash("New passwords do not match.", "error")
            return redirect(url_for("account.index"))
            
        new_hash = generate_password_hash(new_password)
        db.execute("UPDATE users SET password_hash = %s WHERE id = %s", (new_hash, current_user.id))
        db.commit()
        flash("Password changed successfully.", "success")

    return redirect(url_for("account.index"))
