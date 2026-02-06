import os
import time
import secrets
import re
from datetime import datetime, timezone
from utils.timestamps import utc_iso
from services.subscriptions import is_subscription_active

from flask import Blueprint, render_template, request, session, flash, url_for, redirect, current_app
from flask_login import current_user
from slugify import slugify

from database import get_db, create_agent_snapshot
from config import BASE_URL, PUBLIC_BASE_URL, AGENT_PHOTOS_KEY_PREFIX, PROPERTY_PHOTOS_KEY_PREFIX
from constants import (
    ORDER_STATUS_PENDING_PAYMENT,
    DEFAULT_SIGN_COLOR,
    DEFAULT_SIGN_SIZE,
    SIGN_SIZES,
)
from utils.qr_generator import generate_qr
from utils.qr_urls import property_scan_url
from services.printing.yard_sign import generate_yard_sign_pdf, generate_yard_sign_pdf_from_order_row
from utils.uploads import save_image_upload
from utils.pdf_preview import render_pdf_to_web_preview
from utils.sign_options import normalize_sign_size
from utils.storage import get_storage

agent_bp = Blueprint("agent", __name__)


@agent_bp.route("/submit", methods=["GET", "POST"])
def submit():
    if request.method == "POST":
        try:
            # Extract property and agent data
            address = request.form["address"]
            beds = request.form["beds"]
            baths = request.form["baths"]
            sqft = request.form.get("sqft", "")
            price = request.form.get("price", "")
            description = request.form.get("description", "")

            agent_name = request.form["agent_name"]
            brokerage = request.form["brokerage"]
            agent_email = request.form["email"].strip().lower()
            agent_phone = request.form["phone"]

            # URL Inputs & Validation
            from utils.urls import normalize_https_url
            raw_scheduling_url = request.form.get("scheduling_url", "")
            raw_virtual_tour_url = request.form.get("virtual_tour_url", "")
            
            scheduling_url = normalize_https_url(raw_scheduling_url)
            virtual_tour_url = normalize_https_url(raw_virtual_tour_url)

            if raw_scheduling_url and not scheduling_url:
                flash("Invalid scheduling link. Must be a valid HTTPS URL (e.g. https://calendly.com/... )", "error")
                return render_template("submit.html", agent_data=None), 400

            if raw_virtual_tour_url and not virtual_tour_url:
                flash("Invalid virtual tour URL. Must be a valid HTTPS URL.", "error")
                return render_template("submit.html", agent_data=None), 400

            # Extract sign customization options
            sign_color = request.form.get("sign_color", DEFAULT_SIGN_COLOR)
            layout_id = request.form.get("layout_id", "listing_modern_round")
            raw_sign_size = request.form.get("sign_size", DEFAULT_SIGN_SIZE)

            # Normalize sign size using canonical function
            sign_size = normalize_sign_size(raw_sign_size)

            # Strict hex color validation (fallback to default)
            if not re.match(r"^#[0-9a-fA-F]{6}$", sign_color or ""):
                sign_color = DEFAULT_SIGN_COLOR

            # Extract toggle flags (default to False if not checked)
            include_headshot = request.form.get("include_headshot") == "1"
            include_logo = request.form.get("include_logo") == "1"

            db = get_db()
            cursor = db.cursor()

            # Handle Agent Photo Upload
            agent_photo_key = None
            if "agent_photo" in request.files:
                file = request.files["agent_photo"]
                if file and file.filename != "":
                    try:
                        base_name = f"agent_{agent_email.split('@')[0]}_head"
                        agent_photo_key = save_image_upload(file, AGENT_PHOTOS_KEY_PREFIX, base_name, validate_image=True)
                    except ValueError as e:
                        flash(f"Agent photo upload error: {str(e)}", "error")
                        return render_template("submit.html", agent_data=None)

            # Handle Logo Upload
            logo_key = None
            if "logo_file" in request.files:
                file = request.files["logo_file"]
                if file and file.filename != "":
                    try:
                        base_name = f"agent_{agent_email.split('@')[0]}_logo"
                        logo_key = save_image_upload(file, AGENT_PHOTOS_KEY_PREFIX, base_name, validate_image=True)
                    except ValueError as e:
                        flash(f"Logo upload error: {str(e)}", "error")
                        return render_template("submit.html", agent_data=None)

            # Find existing agent
            # Find existing agent
            # [SECURITY] Case-insensitive lookup
            cursor.execute("SELECT id, user_id, email, photo_filename, logo_filename FROM agents WHERE lower(email) = lower(%s)", (agent_email,))
            agent = cursor.fetchone()

            snapshot_photo_key = agent_photo_key
            snapshot_logo_key = logo_key
            can_update_agent = False
            agent_id = None

            if agent:
                agent_id = agent["id"]
                existing_user_id = agent["user_id"]
                
                # Check current values if no new upload
                if not snapshot_photo_key: snapshot_photo_key = agent["photo_filename"]
                if not snapshot_logo_key: snapshot_logo_key = agent["logo_filename"]

                # [SECURITY] Ownership & Blocking Rules
                if existing_user_id is not None:
                     # Agent IS CLAIMED
                     if not current_user.is_authenticated or current_user.id != existing_user_id:
                         # HIJACK ATTEMPT or mismatch -> BLOCK
                         flash("This agent email is already claimed by another user. Please log in as that agent to create listings.", "error")
                         return render_template("submit.html", agent_data=None), 403
                     else:
                         # Owner -> Allow update
                         can_update_agent = True
                
                elif current_user.is_authenticated:
                     # Agent IS UNCLAIMED
                     # Allow claim ONLY if Verified AND Email matches
                     if hasattr(current_user, 'is_verified') and current_user.is_verified and current_user.email.lower() == agent_email.lower():
                         can_update_agent = True
                         cursor.execute("UPDATE agents SET user_id=%s WHERE id=%s", (current_user.id, agent_id))
                     else:
                         # Unverified or Guest or Mismatched Email -> DO NOT CLAIM
                         # Allow creating property but do not touch agent record
                         can_update_agent = False

                if can_update_agent:
                    updates = []
                    params = []
                    
                    updates.extend(["name=%s", "brokerage=%s", "phone=%s"])
                    params.extend([agent_name, brokerage, agent_phone])
                    
                    if agent_photo_key:
                        updates.append("photo_filename=%s")
                        params.append(agent_photo_key)
                    if logo_key:
                        updates.append("logo_filename=%s")
                        params.append(logo_key)
                    
                    # Update scheduling link only if provided and valid (owner can always update)
                    if scheduling_url:
                        updates.append("scheduling_url=%s")
                        params.append(scheduling_url)
                    
                    params.append(agent_id)
                    cursor.execute(f"UPDATE agents SET {', '.join(updates)} WHERE id=%s", tuple(params))
            else:
                # Create New Agent
                # [SECURITY] Link if authenticated (Staging often unverified)
                user_id = None
                if current_user.is_authenticated:
                    user_id = current_user.id

                # SECURITY: Do NOT persist scheduling_url for unclaimed/unverified agent rows.
                scheduling_url_to_store = scheduling_url if user_id else None
                    
                cursor.execute(
                    """
                    INSERT INTO agents (user_id, name, brokerage, email, phone, photo_filename, logo_filename, scheduling_url)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (user_id, agent_name, brokerage, agent_email, agent_phone, agent_photo_key, logo_key, scheduling_url_to_store),
                )
                agent_id = cursor.fetchone()['id']
                snapshot_photo_key = agent_photo_key
                snapshot_logo_key = logo_key

            # ... [Property Creation Logic remains same] ...

            # Create property
            current_time = utc_iso()
            
            # --- HYBRID MONETIZATION & ENTITLEMENT LOGIC ---
            is_pro = False
            if current_user.is_authenticated:
                is_pro = is_subscription_active(current_user.subscription_status)
            
            expires_at = None
            
            if is_pro:
                expires_at = None
            else:
                if current_user.is_authenticated:
                    from services.gating import can_create_property
                    gating_check = can_create_property(current_user.id)
                    if not gating_check['allowed']:
                        flash(f"Free plan limit reached ({gating_check['limit']} listings). Upgrade to Pro.", "error")
                        return render_template("submit.html", agent_data=None), 402

                from datetime import timedelta
                retention_days = int(os.environ.get("FREE_TIER_RETENTION_DAYS", "7"))
                # Ensure timezone-aware usage
                expiry_dt = datetime.now(timezone.utc) + timedelta(days=retention_days)
                expires_at = expiry_dt.isoformat(sep=' ')
            
            cursor.execute(
                """
                INSERT INTO properties (agent_id, address, beds, baths, sqft, price, description, created_at, expires_at, virtual_tour_url)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (agent_id, address, beds, baths, sqft, price, description, current_time, expires_at, virtual_tour_url),
            )
            property_id = cursor.fetchone()['id']

            # ... [Slug/QR generation remains same] ...
            base_slug = slugify(address)
            prop_slug = base_slug
            counter = 2
            cursor.execute("SELECT 1 FROM properties WHERE slug=%s AND id!=%s", (prop_slug, property_id))
            while cursor.fetchone():
                prop_slug = f"{base_slug}-{counter}"
                counter += 1
                cursor.execute("SELECT 1 FROM properties WHERE slug=%s AND id!=%s", (prop_slug, property_id))
            cursor.execute("UPDATE properties SET slug=%s WHERE id=%s", (prop_slug, property_id))

            from utils.qr_codes import generate_unique_code
            qr_code = generate_unique_code(db, length=12)
            cursor.execute("UPDATE properties SET qr_code=%s WHERE id=%s", (qr_code, property_id))

            if "property_photos" in request.files:
                photos = request.files.getlist("property_photos")
                for photo in photos:
                    if photo and photo.filename != "":
                         try:
                            # Re-use existing upload (abbreviated here, assume imports valid)
                            base_name = f"property_{property_id}"
                            safe_key = save_image_upload(photo, PROPERTY_PHOTOS_KEY_PREFIX, base_name, validate_image=True)
                            cursor.execute("INSERT INTO property_photos (property_id, filename) VALUES (%s, %s)", (property_id, safe_key))
                         except: pass

            full_url = property_scan_url(PUBLIC_BASE_URL, qr_code)
            qr_key = generate_qr(full_url, qr_code)

            # Determine Final Keys for PDF
            final_headshot_key = snapshot_photo_key if include_headshot else None
            final_logo_key = snapshot_logo_key if include_logo else None

            # --- MODE CHECK: Property Only (Free) vs Listing Sign (Paid) ---
            mode = request.form.get("mode")
            if mode == 'property_only':
                db.commit() # Ensure insertion is persisted
                current_app.logger.info(f"Property-only mode: Created Property {property_id}")
                # Skip order creation, PDF generation, and checkout
                flash("Property created successfully. Now assign your SmartSign.", "success")
                return redirect(url_for('dashboard.index') + '#smart-signs-section')

            # ... [Order Creation - Standard Flow] ...

            user_id = current_user.id if current_user.is_authenticated else None
            guest_email = None if current_user.is_authenticated else agent_email
            guest_token = secrets.token_urlsafe(32) if not current_user.is_authenticated else None
            token_created_at = datetime.now(timezone.utc) if guest_token else None

            cursor.execute(
                """
                INSERT INTO orders (
                    user_id, guest_email, property_id, status, sign_pdf_path,
                    guest_token, guest_token_created_at, sign_color, sign_size, print_size,
                    order_type,
                    print_product, material, sides
                ) VALUES (%s, %s, %s, %s, NULL, %s, %s, %s, %s, %s, 'sign', %s, %s, %s)
                RETURNING id
                """,
                (
                    user_id, guest_email, property_id, ORDER_STATUS_PENDING_PAYMENT, 
                    guest_token, token_created_at, sign_color, sign_size, sign_size,
                    'yard_sign', 'coroplast_4mm', 'single'  # Canonical print_product/material/sides
                )
            )
            order_id = cursor.fetchone()['id']

            # Snapshot currently doesn't support logo_filename column (schema mismatch?), we'll skip adding it to snapshot for now 
            # to avoid breaking legacy snapshot table unless we migrate that too. 
            # Ideally we should migrate 'agent_snapshots' table too.
            # For now, just pass what fits.
            create_agent_snapshot(
                order_id=order_id,
                name=agent_name,
                brokerage=brokerage,
                email=agent_email,
                phone=agent_phone,
                photo_filename=final_headshot_key,
                logo_filename=final_logo_key, # NEW: Persist logo to snapshot (migration 026)
            )

            # Step 2: Generate PDF
            # Unified Path: Fetch full order row from DB (ensure consistency)
            order_row = db.execute("SELECT * FROM orders WHERE id = %s", (order_id,)).fetchone()
            
            # Use unified generator
            pdf_key = generate_yard_sign_pdf_from_order_row(order_row, db=db)

            # Step 3: Generate WebP preview (returns storage key)
            preview_key = render_pdf_to_web_preview(
                pdf_key,
                order_id=order_id,
                sign_size=sign_size,
            )

            # Step 4: Update order with PDF key, print_size, and preview_key
            cursor.execute(
                "UPDATE orders SET sign_pdf_path = %s, print_size = %s, preview_key = %s WHERE id = %s",
                (pdf_key, sign_size, preview_key, order_id),
            )

            # Save guest token(s) to session
            if guest_token:
                guest_tokens = session.get("guest_tokens", [])
                guest_tokens.append(guest_token)
                session["guest_tokens"] = guest_tokens[-10:]
                # ALSO set singular token for easy access (most recent)
                session["guest_token"] = guest_token

            session["pending_order_id"] = order_id
            db.commit()

            # Build authenticated preview URL
            preview_url = url_for("orders.order_preview", order_id=order_id)
            if guest_token:
                preview_url += f"?guest_token={guest_token}"

            # Get presigned URL for QR debug display if needed (optional)
            storage = get_storage()
            qr_display_url = storage.get_url(qr_key)

            return render_template(
                "assets.html",
                order_id=order_id,
                guest_token=guest_token,
                guest_email=guest_email,
                property_id=property_id,
                qr_file=qr_display_url, 
                preview_url=preview_url,
                property_url=full_url,
                sign_size=sign_size,
                timestamp=int(time.time()),
                order_status=ORDER_STATUS_PENDING_PAYMENT,
                is_locked=False,
            )

        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
            return f"An error occurred: {str(e)}", 500

    # If logged in, pre-fetch agent data
    agent_data = None
    if current_user.is_authenticated:
        db = get_db()
        agent_data = db.execute(
            "SELECT * FROM agents WHERE user_id = %s",
            (current_user.id,),
        ).fetchone()

    return render_template(
        "submit.html", 
        agent_data=agent_data,
        is_property_only=(request.args.get("mode") == "property_only")
    )
