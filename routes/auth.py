from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_user, login_required, logout_user, current_user
from database import get_db
from models import User
from urllib.parse import urlparse, urljoin
import random
from datetime import datetime, timedelta
from services.notifications import send_verification_email

auth_bp = Blueprint('auth', __name__)


def get_limiter():
    """Get limiter from current app - handles blueprint access."""
    return getattr(current_app, 'limiter', None)

def is_safe_url(target):
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ('http', 'https') and \
           ref_url.netloc == test_url.netloc

def generate_verification_code():
    return str(random.randint(100000, 999999))

@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    # Apply rate limit for POST requests only (registration attempts)
    if request.method == "POST":
        limiter = get_limiter()
        if limiter:
            try:
                limiter.limit("5 per minute")(lambda: None)()
            except Exception:
                flash("Too many registration attempts. Please wait a moment.", "error")
                return redirect(url_for("auth.register"))
    # Get next param from either args (GET) or form (POST)
    next_url = request.args.get('next') or request.form.get('next')
    
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password")

        if not full_name or not email or not password:
            flash("All fields are required.", "error")
            return redirect(url_for("auth.register", next=next_url))

        db = get_db()

        user = db.execute(
            "SELECT id FROM users WHERE email = %s", (email,)
        ).fetchone()

        if user:
            flash("Email already exists.", "error")
            return redirect(url_for("auth.register", next=next_url))

        password_hash = generate_password_hash(password)
        
        # Generate verification code
        ver_code = generate_verification_code()
        ver_expires = datetime.now() + timedelta(minutes=15)

        # RETURNING id required for Postgres replacement of lastrowid
        cursor = db.execute(
            "INSERT INTO users (email, password_hash, full_name, verification_code, verification_code_expires_at, is_verified) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
            (email, password_hash, full_name, ver_code, ver_expires, False)
        )
        user_id = cursor.fetchone()['id']

        # Import Upload Utilities
        from utils.uploads import save_image_upload
        from config import AGENT_PHOTOS_KEY_PREFIX
        
        # New Fields
        brokerage = request.form.get("brokerage", "").strip()
        phone = request.form.get("phone", "").strip()
        
        # Handle Files
        headshot_key = None
        logo_key = None
        
        if 'headshot_file' in request.files:
            f = request.files['headshot_file']
            if f and f.filename:
                try:
                    base = f"agent_{user_id}_headshot"
                    headshot_key = save_image_upload(f, AGENT_PHOTOS_KEY_PREFIX, base, validate_image=True)
                except Exception as e:
                    print(f"Registration Headshot Error: {e}")

        if 'logo_file' in request.files:
            f = request.files['logo_file']
            if f and f.filename:
                try:
                    # Storing logos in same bucket for now or use brands check
                    # Using AGENT prefix for simplicity but ideally AGENT_LOGOS
                    base = f"agent_{user_id}_logo"
                    logo_key = save_image_upload(f, AGENT_PHOTOS_KEY_PREFIX, base, validate_image=True)
                except Exception as e:
                    print(f"Registration Logo Error: {e}")

        db.execute(
            "INSERT INTO agents (user_id, name, email, brokerage, phone, photo_filename, logo_filename) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (user_id, full_name, email, brokerage, phone, headshot_key, logo_key)
        )

        # Link Guest Orders (Securely)
        # Only link if email matches AND guest_token matches session (if present)
        # Link Guest Orders (Securely)
        # Only link if email matches AND guest_token matches session (if present)
        from flask import session
        
        # Gather all valid tokens from session
        tokens = set()
        if session.get('guest_token'):
            tokens.add(session.get('guest_token'))
        if session.get('guest_tokens'):
            tokens.update(set(session.get('guest_tokens')))
            
        # Remove empty/None
        tokens = {t for t in tokens if t}
        
        if tokens:
            # We must use list for IN clause
            token_list = list(tokens)
            # Use ANY for Postgres array or IN
            placeholders = ','.join(['%s'] * len(token_list))
            
            # Update Orders
            db.execute(
                f"UPDATE orders SET user_id = %s WHERE guest_email = %s AND guest_token IN ({placeholders}) AND user_id IS NULL",
                (user_id, email, *token_list)
            )
            
            # Clear tokens after successful linking
            session.pop('guest_token', None)
            session.pop('guest_tokens', None)
        else:
            # OPTIONAL: If no guest_token, do we rely on email? 
            pass

        # [SECURITY] Do NOT link agents here. Wait for verification.
        # db.execute("UPDATE agents SET user_id = %s WHERE lower(email) = lower(%s) AND user_id IS NULL", (user_id, email))
        
        db.commit()

        # Send Verification Email
        send_verification_email(email, ver_code)

        # Auto-login the user (unverified)
        user_obj = User(id=user_id, email=email, is_verified=False)
        login_user(user_obj)
        
        if next_url and is_safe_url(next_url):
            from flask import session
            session['next_url'] = next_url
        
        flash("Registration successful! Please verify your email.", "info")
        return redirect(url_for("auth.verify_email"))

    return render_template("register.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    # Apply rate limit for POST requests only (login attempts)
    if request.method == "POST":
        limiter = get_limiter()
        if limiter:
            try:
                limiter.limit("5 per minute", key_func=lambda: request.form.get('email', 'unknown'))(lambda: None)()
            except Exception:
                flash("Too many login attempts. Please wait a moment.", "error")
                return redirect(url_for("auth.login"))
    # Get next param from either args (GET) or form (POST)
    next_url = request.args.get('next') or request.form.get('next')

    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE email = %s", (email,)).fetchone()
        
        if user and check_password_hash(user['password_hash'], password):
            user_obj = User(
                id=user['id'], 
                email=user['email'],
                is_admin=bool(dict(user).get('is_admin', 0)),
                is_verified=bool(dict(user).get('is_verified', 0)),
                subscription_status=dict(user).get('subscription_status', 'free')
            )
            # Link any guest orders (Securely)
            from flask import session
            
            # Gather all valid tokens from session
            tokens = set()
            if session.get('guest_token'):
                tokens.add(session.get('guest_token'))
            if session.get('guest_tokens'):
                tokens.update(set(session.get('guest_tokens')))
            
            # Remove empty/None
            tokens = {t for t in tokens if t}
            
            if tokens:
                token_list = list(tokens)
                placeholders = ','.join(['%s'] * len(token_list))
                
                db.execute(
                    f"UPDATE orders SET user_id = %s WHERE guest_email = %s AND guest_token IN ({placeholders}) AND user_id IS NULL",
                    (user['id'], email, *token_list)
                )
                
                # Clear tokens
                session.pop('guest_token', None)
                session.pop('guest_tokens', None)
            
            # [SECURITY] Do NOT link agents here unverified.
            # Only link if user is already verified (which they are if they pass login and check below)
            # But the logic below handles redirection if UNVERIFIED. 
            # We must only link if user.is_verified is True.
            
            if user_obj.is_verified:
                db.execute(
                     "UPDATE agents SET user_id = %s WHERE lower(email) = lower(%s) AND user_id IS NULL",
                     (user['id'], email)
                )
            db.commit()
            
            login_user(user_obj)
            
            # Check verification status
            if not user_obj.is_verified:
                # Store next_url for post-verification redirect
                if next_url and is_safe_url(next_url):
                    from flask import session
                    session['next_url'] = next_url
                return redirect(url_for("auth.verify_email"))
            
            # Safe redirect to next_url if present
            if next_url and is_safe_url(next_url):
                return redirect(next_url)
                
            return redirect(url_for("dashboard.index"))
        else:
            flash("Invalid email or password.", "error")
            return redirect(url_for("auth.login", next=next_url))
            
    return render_template("login.html")

@auth_bp.route("/verify", methods=["GET", "POST"])
@login_required
def verify_email():
    if current_user.is_verified:
        return redirect(url_for("dashboard.index"))
        
    if request.method == "POST":
        code = request.form.get("code", "").strip()
        
        db = get_db()
        user_row = db.execute("SELECT * FROM users WHERE id = %s", (current_user.id,)).fetchone()
        
        if not user_row:
            logout_user()
            return redirect(url_for("auth.login"))

        stored_code = user_row['verification_code']
        expires_at = user_row['verification_code_expires_at']
        
        # Check code
        if not stored_code or stored_code != code:
            flash("Invalid verification code.", "error")
            return redirect(url_for("auth.verify_email"))
            
        # Check expiry
        if isinstance(expires_at, str):
            try:
                expires_at = datetime.fromisoformat(expires_at)
            except:
                pass # Already parsed?
                
        if expires_at and datetime.now() > expires_at:
            flash("Verification code expired. Please request a new one.", "error")
            return redirect(url_for("auth.verify_email"))
            
        # Success
        db.execute("UPDATE users SET is_verified = %s, verification_code = NULL WHERE id = %s", (True, current_user.id))
        
        # [SECURITY] Link agents NOW that user is verified
        db.execute(
             "UPDATE agents SET user_id = %s WHERE lower(email) = lower(%s) AND user_id IS NULL",
             (current_user.id, current_user.email)
        )
        
        db.commit()
        
        # Update session user
        current_user.is_verified = True
        flash("Email verified successfully!", "success")
        
        # Check for deferred redirect
        from flask import session
        next_url = session.pop('next_url', None)
        if next_url:
            return redirect(next_url)
            
        return redirect(url_for("dashboard.index"))
        
    return render_template("verify_email.html")

@auth_bp.route("/resend-verification")
@login_required
def resend_verification():
    if current_user.is_verified:
        return redirect(url_for("dashboard.index"))

    db = get_db()
    ver_code = generate_verification_code()
    ver_expires = datetime.now() + timedelta(minutes=15)
    
    db.execute(
        "UPDATE users SET verification_code = %s, verification_code_expires_at = %s WHERE id = %s",
        (ver_code, ver_expires, current_user.id)
    )
    db.commit()
    
    send_verification_email(current_user.email, ver_code)
    flash("New verification code sent!", "info")
    return redirect(url_for("auth.verify_email"))

@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("public.landing"))
