import os
import time
import secrets
import re
from datetime import datetime, timezone
from utils.timestamps import utc_iso
from services.subscriptions import is_subscription_active

from flask import Blueprint, render_template, request, session, flash, url_for
from flask_login import current_user
from slugify import slugify

from database import get_db, create_agent_snapshot
from config import BASE_URL, AGENT_PHOTOS_KEY_PREFIX, PROPERTY_PHOTOS_KEY_PREFIX
from constants import (
    ORDER_STATUS_PENDING_PAYMENT,
    DEFAULT_SIGN_COLOR,
    DEFAULT_SIGN_SIZE,
    SIGN_SIZES,
)
from utils.qr_generator import generate_qr
from utils.pdf_generator import generate_pdf_sign
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
            agent_email = request.form["email"]
            agent_phone = request.form["phone"]

            # Extract sign customization options
            sign_color = request.form.get("sign_color", DEFAULT_SIGN_COLOR)
            raw_sign_size = request.form.get("sign_size", DEFAULT_SIGN_SIZE)

            # Normalize sign size using canonical function
            sign_size = normalize_sign_size(raw_sign_size)

            # Strict hex color validation (fallback to default)
            if not re.match(r"^#[0-9a-fA-F]{6}$", sign_color or ""):
                sign_color = DEFAULT_SIGN_COLOR

            db = get_db()
            cursor = db.cursor()

            # Handle Agent Photo Upload
            # We now use relative folders for storage keys
            
            agent_photo_key = None
            if "agent_photo" in request.files:
                file = request.files["agent_photo"]
                if file and file.filename != "":
                    try:
                        base_name = f"agent_{agent_email.split('@')[0]}"
                        # Returns storage key, e.g. "uploads/agents/filename.jpg"
                        agent_photo_key = save_image_upload(
                            file,
                            AGENT_PHOTOS_KEY_PREFIX,
                            base_name,
                            validate_image=True,
                        )
                    except ValueError as e:
                        flash(f"Agent photo upload error: {str(e)}", "error")
                        return render_template("submit.html", agent_data=None)

            # Find existing agent or create
            # SECURITY: Implement Rules A/B/C for agent profile protection
            cursor.execute("SELECT id, user_id, photo_filename FROM agents WHERE email = %s", (agent_email,))
            agent = cursor.fetchone()

            # === SECURITY: Ownership Gate ===
            if agent:
                existing_user_id = agent["user_id"]
                if existing_user_id is not None:
                    # Agent is claimed by a user - verify ownership
                    if not current_user.is_authenticated or current_user.id != existing_user_id:
                        flash(
                            "This email is already linked to an account. Please log in to continue.",
                            "error"
                        )
                        return render_template("submit.html", agent_data=None), 403

            # Track which photo key to use for rendering (may differ from DB update)
            snapshot_photo_key = agent_photo_key
            can_update_agent = False

            if agent:
                agent_id = agent["id"]
                existing_user_id = agent["user_id"]

                # Rule A: Authenticated owner can update
                if existing_user_id is not None:
                    if current_user.is_authenticated and current_user.id == existing_user_id:
                        can_update_agent = True
                else:
                    # Rule C: Agent without user_id - allow claim/update if authenticated
                    if current_user.is_authenticated:
                        can_update_agent = True
                        cursor.execute(
                            "UPDATE agents SET user_id = %s WHERE id = %s",
                            (current_user.id, agent_id),
                        )

                # Only update agent record if allowed
                if can_update_agent:
                    if agent_photo_key:
                        cursor.execute(
                            """
                            UPDATE agents
                            SET name = %s, brokerage = %s, phone = %s, photo_filename = %s
                            WHERE id = %s
                            """,
                            (agent_name, brokerage, agent_phone, agent_photo_key, agent_id),
                        )
                    else:
                        cursor.execute(
                            """
                            UPDATE agents
                            SET name = %s, brokerage = %s, phone = %s
                            WHERE id = %s
                            """,
                            (agent_name, brokerage, agent_phone, agent_id),
                        )
                else:
                    # Use submitted photo if provided, otherwise use existing from agent
                    # Note: agent["photo_filename"] now stores a key
                    if not snapshot_photo_key and agent["photo_filename"]:
                        snapshot_photo_key = agent["photo_filename"]
            else:
                # New agent - create it
                user_id = current_user.id if current_user.is_authenticated else None
                # Store key in photo_filename column
                # RETURNING id required
                cursor.execute(
                    """
                    INSERT INTO agents (user_id, name, brokerage, email, phone, photo_filename)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (user_id, agent_name, brokerage, agent_email, agent_phone, agent_photo_key),
                )
                agent_id = cursor.fetchone()['id']

            # Create property
            current_time = utc_iso()
            
            # --- HYBRID MONETIZATION & ENTITLEMENT LOGIC ---
            is_pro = False
            if current_user.is_authenticated:
                is_pro = is_subscription_active(current_user.subscription_status)
            
            expires_at = None
            
            if is_pro:
                # Pro Users: No expiry
                expires_at = None
            else:
                # Free Users: Enforce Limit & Expiry
                
                # 1. Enforce Max Active Properties Limit using canonical gating service
                if current_user.is_authenticated:
                    from services.gating import can_create_property
                    gating_check = can_create_property(current_user.id)
                    
                    if not gating_check['allowed']:
                        # Track event for analytics
                        try:
                            from services.events import track_event
                            track_event(
                                'upgrade_prompt_shown',
                                user_id=current_user.id,
                                meta={'reason': 'max_listings', 'limit': gating_check['limit'], 'current': gating_check['current']}
                            )
                        except Exception:
                            pass  # Best-effort tracking
                        
                        flash(f"Free plan supports {gating_check['limit']} active listing. Upgrade to Pro for unlimited listings.", "error")
                        return render_template("submit.html", agent_data=None, upgrade_reason='max_listings'), 402

                # 2. Set Expiry
                from datetime import timedelta
                retention_days = int(os.environ.get("FREE_TIER_RETENTION_DAYS", "7"))
                expiry_dt = datetime.now(timezone.utc) + timedelta(days=retention_days)
                expires_at = expiry_dt.isoformat(sep=' ')
            
            # RETURNING id required
            cursor.execute(
                """
                INSERT INTO properties (agent_id, address, beds, baths, sqft, price, description, created_at, expires_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (agent_id, address, beds, baths, sqft, price, description, current_time, expires_at),
            )
            property_id = cursor.fetchone()['id']

            # Create canonical slug for property URLs
            base_slug = slugify(address)
            prop_slug = base_slug
            counter = 2
            cursor.execute(
                "SELECT 1 FROM properties WHERE slug = %s AND id != %s",
                (prop_slug, property_id),
            )
            while cursor.fetchone():
                prop_slug = f"{base_slug}-{counter}"
                counter += 1
                cursor.execute(
                    "SELECT 1 FROM properties WHERE slug = %s AND id != %s",
                    (prop_slug, property_id),
                )

            cursor.execute("UPDATE properties SET slug = %s WHERE id = %s", (prop_slug, property_id))

            # Generate unique QR shortcode using the global uniqueness helper
            # Single source of truth: utils/qr_codes.generate_unique_code
            from utils.qr_codes import generate_unique_code
            qr_code = generate_unique_code(db, length=12)
            cursor.execute("UPDATE properties SET qr_code = %s WHERE id = %s", (qr_code, property_id))

            # Handle property photos
            if "property_photos" in request.files:
                photos = request.files.getlist("property_photos")
                for photo in photos:
                    if photo and photo.filename != "":
                        try:
                            base_name = f"property_{property_id}"
                            safe_key = save_image_upload(
                                photo,
                                PROPERTY_PHOTOS_KEY_PREFIX,
                                base_name,
                                validate_image=True,
                            )
                            cursor.execute(
                                "INSERT INTO property_photos (property_id, filename) VALUES (%s, %s)",
                                (property_id, safe_key),
                            )
                        except ValueError as e:
                            print(f"[Submit] Property photo upload warning: {e}")
                            continue

            # Build QR URL
            full_url = f"{BASE_URL}/r/{qr_code}"

            # Generate QR code - returns a storage key
            qr_key = generate_qr(full_url, qr_code)

            # Resolve agent photo key for rendering (snapshot_photo_key already set logic above)
            final_agent_photo_key = snapshot_photo_key
            if not final_agent_photo_key and agent:
                 # Double check from DB if missed
                 existing = db.execute("SELECT photo_filename FROM agents WHERE id = %s", (agent_id,)).fetchone()
                 if existing:
                     final_agent_photo_key = existing["photo_filename"]

            # ===================================================================
            # Insert order FIRST, then generate PDF with order_id
            # ===================================================================

            # Prepare order metadata
            user_id = current_user.id if current_user.is_authenticated else None
            guest_email = None if current_user.is_authenticated else agent_email

            guest_token = None
            if not current_user.is_authenticated:
                guest_token = secrets.token_urlsafe(32)

            token_created_at = datetime.now(timezone.utc) if guest_token else None

            # Step 1: Insert order with sign_pdf_path = NULL
            # RETURNING id required
            cursor.execute(
                """
                INSERT INTO orders (
                    user_id, guest_email, property_id, status, sign_pdf_path,
                    guest_token, guest_token_created_at, sign_color, sign_size, print_size,
                    order_type
                ) VALUES (%s, %s, %s, %s, NULL, %s, %s, %s, %s, %s, 'listing_sign')
                RETURNING id
                """,
                (
                    user_id,
                    guest_email,
                    property_id,
                    ORDER_STATUS_PENDING_PAYMENT,
                    guest_token,
                    token_created_at,
                    sign_color,
                    sign_size,
                    sign_size,  # print_size = sign_size for consistency
                ),
            )
            order_id = cursor.fetchone()['id']

            # Create agent snapshot
            create_agent_snapshot(
                order_id=order_id,
                name=agent_name,
                brokerage=brokerage,
                email=agent_email,
                phone=agent_phone,
                photo_filename=final_agent_photo_key,
            )

            # Step 2: Generate PDF (returns storage key)
            pdf_key = generate_pdf_sign(
                address,
                beds,
                baths,
                sqft,
                price,
                agent_name,
                brokerage,
                agent_email,
                agent_phone,
                qr_key,  # Passing key
                final_agent_photo_key, # Passing key
                sign_color,
                sign_size,
                order_id=order_id,
                qr_value=full_url,
            )

            # Step 3: Generate WebP preview (returns storage key)
            preview_key = render_pdf_to_web_preview(
                pdf_key,
                order_id=order_id,
                sign_size=sign_size,
            )

            # Step 4: Update order with PDF key and print_size
            cursor.execute(
                "UPDATE orders SET sign_pdf_path = %s, print_size = %s WHERE id = %s",
                (pdf_key, sign_size, order_id),
            )

            # Save guest token(s) to session
            if guest_token:
                guest_tokens = session.get("guest_tokens", [])
                guest_tokens.append(guest_token)
                session["guest_tokens"] = guest_tokens[-10:]

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

    return render_template("submit.html", agent_data=agent_data)
