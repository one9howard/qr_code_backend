"""
Dashboard Routes - Agent Dashboard with Properties and Leads.

Provides:
- GET /dashboard - Main dashboard view
- POST /dashboard/delete/<id> - Delete property
- GET/POST /dashboard/edit/<id> - Edit property
"""
import os
from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from database import get_db
from config import PROPERTY_PHOTOS_DIR, PROPERTY_PHOTOS_KEY_PREFIX
from utils.uploads import save_image_upload
from utils.storage import get_storage

dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')

# Free tier limit for leads visibility
FREE_LEAD_LIMIT = 2


@dashboard_bp.route("/")
@login_required
def index():
    """
    Main dashboard view.
    Shows properties, leads, and analytics (Pro only).
    """
    db = get_db()
    
    # 1. Fetch Agent (User Profile) - Required for dashboard access
    agent = db.execute(
        "SELECT * FROM agents WHERE user_id = %s", 
        (current_user.id,)
    ).fetchone()

    if not agent:
        flash("Agent profile missing. Please contact support or re-register.", "error")
        return redirect(url_for("auth.logout"))
    
    # 2. Fetch Properties & Build View Model (Task 3)
    raw_properties = db.execute('''
        SELECT 
            p.*,
            COUNT(s.id) as scan_count,
            MAX(s.scanned_at) as last_scan
        FROM properties p
        LEFT JOIN qr_scans s ON p.id = s.property_id
        WHERE p.agent_id IN (SELECT id FROM agents WHERE user_id = %s)
        GROUP BY p.id
        ORDER BY p.created_at DESC
    ''', (current_user.id,)).fetchall()
    
    total_listings = len(raw_properties)
    total_views = sum(p['scan_count'] for p in raw_properties)
    
    # Enrich properties with gating status (View Model)
    from services.gating import get_property_gating_status
    properties_view = []
    
    for p in raw_properties:
        gating = get_property_gating_status(p['id'])
        
        # Determine status label
        if gating['is_paid']:
            if gating.get('paid_via') == 'subscription':
                status_label = "Pro (Subscription)"
                status_color = "pro"
            elif gating.get('paid_via') in ('listing_unlock', 'sign_order'):
                status_label = "Unlocked (Purchase)"
                status_color = "paid_unlock"
            else:
                # Fallback for old data
                status_label = "Paid"
                status_color = "pro"
        elif gating['is_expired']:
            status_label = "Expired"
            status_color = "expired"
        else:
            status_label = "Active (Free)"
            status_color = "active"
        
        # Format created_date as YYYY-MM-DD
        created_raw = p['created_at']
        if created_raw:
            # Handle string or datetime
            created_date = str(created_raw)[:10]
        else:
            created_date = "N/A"
            
        # Determine sign type (MVP: Simple N+1 query)
        sign_type = None
        # Valid orders: sign, listing_sign, or smart_riser
        has_listing_sign = db.execute(
            "SELECT 1 FROM orders WHERE property_id=%s AND order_type IN ('sign', 'listing_sign', 'smart_riser') LIMIT 1", 
            (p['id'],)
        ).fetchone()
        
        has_smart_sign = db.execute(
            "SELECT 1 FROM sign_assets WHERE active_property_id=%s LIMIT 1",
            (p['id'],)
        ).fetchone()
        
        if has_smart_sign:
            sign_type = "Smart Sign"
        elif has_listing_sign:
            sign_type = "Listing Sign"
            
        properties_view.append({
            "id": p['id'],
            "address": p['address'],
            "price": p['price'],
            "created_date": created_date,  # Formatted date
            "scan_count": p['scan_count'],
            "status_label": status_label,
            "status_color": status_color,
            "sign_type": sign_type,
            "days_remaining": gating['days_remaining'],
            "locked_reason": gating['locked_reason']
        })
    
    # 3. Fetch Leads (with tier-based limiting)
    is_pro = current_user.is_pro
    
    total_lead_count = db.execute(
        "SELECT COUNT(*) as cnt FROM leads WHERE agent_id IN (SELECT id FROM agents WHERE user_id = %s)",
        (current_user.id,)
    ).fetchone()['cnt']
    
    # Build leads query with optional limit
    leads_query = """
        SELECT l.*, p.address as property_address 
        FROM leads l
        JOIN properties p ON l.property_id = p.id
        WHERE l.agent_id IN (SELECT id FROM agents WHERE user_id = %s)
        ORDER BY l.created_at DESC
    """
    if not is_pro:
        leads_query += f" LIMIT {FREE_LEAD_LIMIT}"
    
    leads = db.execute(leads_query, (current_user.id,)).fetchall()
    
    # 4. Fetch Pro Analytics (if Pro tier)
    analytics = None
    chart_data = None
    
    if is_pro:
        from services.analytics import get_dashboard_analytics
        from datetime import datetime, timedelta, timezone
        
        # Pass user_id instead of agent_id to aggregate properly
        analytics = get_dashboard_analytics(user_id=current_user.id)
        
        # Prepare chart data: fill in missing dates with zeros
        # Generate last 30 days as labels (using UTC for consistency with analytics)
        today = datetime.now(timezone.utc).date()
        labels = [(today - timedelta(days=i)).isoformat() for i in range(29, -1, -1)]
        
        # Map existing data by date
        leads_by_date = {item['date']: item['count'] for item in (analytics.get('leads_over_time') or [])}
        scans_by_date = {item['date']: item['count'] for item in (analytics.get('qr_scans_over_time') or [])}
        
        # Fill in data (zeros for missing dates)
        leads_counts = [leads_by_date.get(date, 0) for date in labels]
        scans_counts = [scans_by_date.get(date, 0) for date in labels]
        
        has_data = sum(leads_counts) > 0 or sum(scans_counts) > 0
        
        # Pass as dict (template will use tojson filter)
        chart_data = {
            'labels': labels,
            'leads': leads_counts,
            'scans': scans_counts,
            'has_data': has_data
        }
    else:
        chart_data = {'labels': [], 'leads': [], 'scans': [], 'has_data': False}

    # Fetch dynamic prices for UI
    from services.stripe_config import get_configured_prices
    prices = get_configured_prices()
    
    # 5. Fetch SmartSigns (Phase 1)
    from services.smart_signs import SmartSignsService
    sign_assets = SmartSignsService.get_user_assets(current_user.id)

    return render_template(
        "dashboard.html", 
        agent=agent,
        properties=properties_view, # Use View Model
        total_listings=total_listings,
        total_views=total_views,
        leads=leads,
        total_lead_count=total_lead_count,
        is_pro=is_pro,
        free_lead_limit=FREE_LEAD_LIMIT,
        analytics=analytics,
        chart_data=chart_data,
        prices=prices,
        sign_assets=sign_assets
    )


@dashboard_bp.route("/delete/<int:property_id>", methods=["POST"])
@login_required
def delete_property(property_id):
    """Delete a property owned by the current user."""
    db = get_db()
    
    # 1. Verify Ownership
    row = db.execute(
        "SELECT 1 FROM properties WHERE id = %s AND agent_id IN (SELECT id FROM agents WHERE user_id = %s)", 
        (property_id, current_user.id)
    ).fetchone()
    
    if not row:
        flash("Access denied or property not found.", "error")
        return redirect(url_for('dashboard.index'))
        
    # 2. Perform Complete Deletion
    from services.properties import delete_property_fully
    if delete_property_fully(property_id):
        flash("Property deleted.", "success")
    else:
        flash("Error deleting property data.", "error")
        
    return redirect(url_for('dashboard.index'))


@dashboard_bp.route("/edit/<int:property_id>", methods=["GET", "POST"])
@login_required
def edit_property(property_id):
    """Edit a property owned by the current user."""
    db = get_db()
    
    # Verify ownership via JOIN
    property_row = db.execute(
        """
        SELECT p.* 
        FROM properties p
        JOIN agents a ON p.agent_id = a.id
        WHERE p.id = %s AND a.user_id = %s
        """, 
        (property_id, current_user.id)
    ).fetchone()

    if not property_row:
        flash("Property not found or access denied.", "error")
        return redirect(url_for('dashboard.index'))
    
    if request.method == "POST":
        address = request.form["address"]
        beds = request.form["beds"]
        baths = request.form["baths"]
        sqft = request.form.get("sqft", "")
        price = request.form.get("price", "")
        description = request.form.get("description", "")
        
        # Update property
        db.execute('''
            UPDATE properties 
            SET address = %s, beds = %s, baths = %s, sqft = %s, price = %s, description = %s
            WHERE id = %s
        ''', (address, beds, baths, sqft, price, description, property_id))

        # Handle Photo Deletions
        storage = get_storage()
        delete_photos = request.form.getlist("delete_photos")
        for photo_id in delete_photos:
            photo = db.execute(
                "SELECT filename FROM property_photos WHERE id = %s AND property_id = %s", 
                (photo_id, property_id)
            ).fetchone()
            if photo:
                try:
                    storage.delete(photo['filename'])
                except Exception:
                    pass
                db.execute("DELETE FROM property_photos WHERE id = %s", (photo_id,))

        # Handle New Photo Uploads
        if 'property_photos' in request.files:
            photos = request.files.getlist('property_photos')
            valid_photos = [p for p in photos if p and p.filename != '']
            
            if valid_photos:
                # Check Limit
                from services.gating import get_property_gating_status
                gating = get_property_gating_status(property_id)
                
                if not gating['is_paid']:
                    current_count = db.execute(
                        "SELECT COUNT(*) as cnt FROM property_photos WHERE property_id = %s",
                        (property_id,)
                    ).fetchone()['cnt']
                    
                    if current_count + len(valid_photos) > gating['max_photos']:
                        flash(f"Free Tier Limit: You can only have {gating['max_photos']} photo(s). Upgrade for unlimited.", "error")
                        valid_photos = []

                for photo in valid_photos:
                    try:
                        base_name = f"property_{property_id}"
                        safe_key = save_image_upload(
                            photo,
                            PROPERTY_PHOTOS_KEY_PREFIX,
                            base_name,
                            validate_image=True
                        )
                        db.execute(
                            "INSERT INTO property_photos (property_id, filename) VALUES (%s, %s)", 
                            (property_id, safe_key)
                        )
                    except ValueError as e:
                        flash(f"Image upload failed: {str(e)}", "error")
                        continue

        db.commit()
        flash("Property updated successfully.", "success")
        return redirect(url_for('dashboard.index'))
    
    # GET request - fetch photos for display
    photos = db.execute(
        "SELECT * FROM property_photos WHERE property_id = %s", 
        (property_id,)
    ).fetchall()
        
    return render_template("edit_property.html", property=property_row, photos=photos)


# =============================================================================
# SmartSigns Management (MVP)
# =============================================================================

@dashboard_bp.route("/smart-signs/create", methods=["POST"])
@login_required
def create_smart_sign():
    """Manual creation for Pro users (Phase 1) - Creates UNACTIVATED draft asset."""
    if not current_user.is_pro:
        flash("SmartSigns are a Pro feature. Upgrade to create assets manually.", "error")
        return redirect(url_for('dashboard.index'))
    
    from services.smart_signs import SmartSignsService
    
    try:
        # Option B enforcement: Assets are ALWAYS created unactivated
        # Activation requires a paid SmartSign order
        asset = SmartSignsService.create_asset(
            user_id=current_user.id
            # No activated param - assets are always unactivated
        )
        flash(
            f"SmartSign created! Code: {asset['code']}. "
            f"Purchase a SmartSign to activate it.",
            "info"
        )
    except Exception as e:
        flash(f"Error creating SmartSign: {e}", "error")
        
    return redirect(url_for('dashboard.index', _anchor='smart-signs-section'))


@dashboard_bp.route("/smart-signs/<int:asset_id>/assign", methods=["POST"])
@login_required
def assign_smart_sign(asset_id):
    """Assign or Reassign a SmartSign (Pro only)."""
    from services.smart_signs import SmartSignsService
    
    property_id = request.form.get("property_id")
    if property_id == "unassigned":
        property_id = None
    else:
        try:
            property_id = int(property_id)
        except (TypeError, ValueError):
            flash("Invalid property selection.", "error")
            return redirect(url_for('dashboard.index', _anchor='smart-signs-section'))
    
    # Determine reason code for tracking
    reason_code = None
    
    try:
        SmartSignsService.assign_asset(asset_id, property_id, current_user.id)
        flash("SmartSign assignment updated.", "success")
    except ValueError as e:
        error_msg = str(e)
        # Determine reason code from error message
        if "frozen" in error_msg.lower():
            reason_code = "asset_frozen"
        elif "activated" in error_msg.lower():
            reason_code = "not_activated"
        else:
            reason_code = "validation_error"
        
        # Track event
        try:
            from services.events import track_event
            track_event(
                'upgrade_prompt_shown',
                user_id=current_user.id,
                meta={'reason': 'smart_sign_reassign_blocked', 'blocked_reason': reason_code}
            )
        except Exception:
            pass  # Best-effort tracking
        
        flash(error_msg, "error")
    except PermissionError as e:
        error_msg = str(e)
        reason_code = "upgrade_required"
        
        # Track event
        try:
            from services.events import track_event
            track_event(
                'upgrade_prompt_shown',
                user_id=current_user.id,
                meta={'reason': 'smart_sign_reassign_blocked', 'blocked_reason': reason_code}
            )
        except Exception:
            pass  # Best-effort tracking
        
        flash(f"{error_msg} Upgrade to Pro to reassign SmartSigns.", "error")
    except Exception as e:
        flash("Error assigning SmartSign.", "error")
        print(f"[SmartSigns] Assign Error: {e}")
        
    return redirect(url_for('dashboard.index', _anchor='smart-signs-section'))
