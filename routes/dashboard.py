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
    """    Main dashboard view.
    Shows properties, leads, and analytics (Integrated Phase 5).
    """
    db = get_db()

    # --- Phase 5: Analytics Service Integration ---
    from services.analytics import per_agent_rollup, per_property_metrics

    # 1. Main Metrics Rollup
    metrics = per_agent_rollup(current_user.id)

    # 2. Determine all agent IDs linked to this user (supports multiple agent rows)
    agent_rows = db.execute(
        "SELECT id FROM agents WHERE user_id = %s",
        (current_user.id,)
    ).fetchall()
    agent_ids = [r['id'] for r in agent_rows] if agent_rows else []
    agent_ids_param = agent_ids if agent_ids else [-1]  # Safe sentinel

    # 3. Fetch Properties & Build Listings Data
    listings_data = []
    properties = []

    if agent_ids:
        properties = db.execute(
            """
            SELECT
                p.id,
                p.address,
                p.slug,
                p.qr_code,
                p.created_at,
                (SELECT filename FROM property_photos pp WHERE pp.property_id = p.id LIMIT 1) AS photo_filename
            FROM properties p
            WHERE p.agent_id = ANY(%s)
            ORDER BY p.created_at DESC
            """,
            (agent_ids_param,)
        ).fetchall()

        for p in properties:
            pm = per_property_metrics(p['id'], range_days=7)
            listings_data.append({
                "id": p['id'],
                "address": p['address'],
                "slug": p['slug'],
                "thumbnail": p['photo_filename'],
                "qr_code": p['qr_code'],
                "scans_7d": pm['scans']['total'],
                "scans_trend": pm['scans']['delta'],
                "views_7d": pm['views']['total'],
                "views_trend": pm['views']['delta'],
                "leads_7d": pm['leads']['total'],
                "leads_trend": pm['leads']['delta'],
                "cta_7d": pm['ctas']['total'],
                "last_activity": pm['last_activity']['summary'],
                "insights": pm['insights'],
            })

    # 4. Today's Focus Cards
    today_cards = []
    if agent_ids:
        for p in listings_data:
            if p['scans_7d'] == 0:
                today_cards.append({
                    'type': 'warning',
                    'title': 'Zero Visibility',
                    'message': f"{p['address']} has 0 scans in the last 7 days.",
                    'action': 'Check Sign Placement',
                    'link': url_for('properties.property_page', slug=p['slug'])
                })

            if p['scans_trend'] > 50 and p['scans_7d'] > 5:
                today_cards.append({
                    'type': 'success',
                    'title': 'Gaining Momentum',
                    'message': f"{p['address']} scans up {p['scans_trend']}% WoW!",
                    'action': 'View Analytics',
                    'link': url_for('dashboard.property_analytics', property_id=p['id'])
                })

            if p['cta_7d'] > 0 and p['leads_7d'] == 0:
                today_cards.append({
                    'type': 'info',
                    'title': 'High Intent, No Leads',
                    'message': f"{p['address']} has {p['cta_7d']} engagements but no leads.",
                    'action': 'Review Pricing',
                    'link': url_for('dashboard.edit_property', property_id=p['id'])
                })

    # 5. SmartSigns (Legacy/MVP Compat) with Performance Metrics
    from services.smart_signs import SmartSignsService
    sign_assets = SmartSignsService.get_user_assets(current_user.id)
    
    # 5b. Compute per-asset scans/leads/conversion
    asset_ids = [a['id'] for a in sign_assets] if sign_assets else [-1]
    
    # Query scans per asset from qr_scans
    scans_result = db.execute("""
        SELECT sign_asset_id, COUNT(*) as count 
        FROM qr_scans 
        WHERE sign_asset_id = ANY(%s) 
        GROUP BY sign_asset_id
    """, (asset_ids,)).fetchall()
    scans_by_asset = {r['sign_asset_id']: r['count'] for r in scans_result}
    
    # Query leads per asset from leads table
    leads_result = db.execute("""
        SELECT sign_asset_id, COUNT(*) as count 
        FROM leads 
        WHERE sign_asset_id = ANY(%s) 
        GROUP BY sign_asset_id
    """, (asset_ids,)).fetchall()
    leads_by_asset = {r['sign_asset_id']: r['count'] for r in leads_result}
    
    # Enrich sign_assets with metrics
    for asset in sign_assets:
        aid = asset['id']
        scans = scans_by_asset.get(aid, 0)
        leads = leads_by_asset.get(aid, 0)
        asset['scans'] = scans
        asset['leads'] = leads
        
        # Conversion rate: show "—" if insufficient data
        if scans < 5:
            asset['conversion'] = "—"
        else:
            conv = (leads / scans) * 100
            asset['conversion'] = f"{conv:.1f}%"

    # 6. Leads (Recent)
    leads = db.execute(
        """
        SELECT l.*, p.address AS property_address
        FROM leads l
        JOIN properties p ON l.property_id = p.id
        WHERE p.agent_id = ANY(%s)
        ORDER BY l.created_at DESC
        LIMIT 10
        """,
        (agent_ids_param,)
    ).fetchall()

    # 7. Listing Signs (orders with order_type='sign')
    listing_signs_raw = db.execute(
        """
        SELECT 
            o.id as order_id,
            p.id,
            p.address,
            p.price,
            o.status,
            o.created_at,
            (SELECT COUNT(*) FROM qr_scans WHERE property_id = p.id) as scan_count
        FROM orders o
        JOIN properties p ON o.property_id = p.id
        WHERE o.user_id = %s 
          AND o.order_type = 'sign' 
          AND o.status = 'paid'
        ORDER BY o.created_at DESC
        """,
        (current_user.id,)
    ).fetchall()
    
    # Enrich with status labels for display
    listing_signs = []
    for row in listing_signs_raw:
        from services.gating import get_property_gating_status
        gating = get_property_gating_status(row['id'])
        
        if gating['is_expired'] and not gating['is_paid']:
            status_label = 'Expired'
            status_color = 'expired'
        elif gating['is_paid']:
            status_label = 'Active'
            status_color = 'active'
        else:
            status_label = 'Preview'
            status_color = 'pending'
        
        listing_signs.append({
            'id': row['id'],
            'order_id': row['order_id'],
            'address': row['address'],
            'price': row['price'],
            'scan_count': row['scan_count'] or 0,
            'status_label': status_label,
            'status_color': status_color,
        })

    # 8. Onboarding Activation Checklist (Phase 1)
    # Compute all flags server-side for template simplicity
    smart_sign_count = len(sign_assets)
    has_smartsigns = smart_sign_count > 0
    has_assigned_sign = any(a.get('active_property_id') for a in sign_assets)
    
    # Check if user has any scans (for their SmartSigns)
    has_scan = False
    if has_smartsigns:
        scan_check = db.execute("""
            SELECT 1 FROM qr_scans 
            WHERE sign_asset_id = ANY(%s) 
            LIMIT 1
        """, (asset_ids,)).fetchone()
        has_scan = scan_check is not None
    
    # Lead counts for checklist and first-lead highlight
    lead_count_result = db.execute("""
        SELECT COUNT(*) as total FROM leads l
        JOIN properties p ON l.property_id = p.id
        WHERE p.agent_id = ANY(%s)
    """, (agent_ids_param,)).fetchone()
    lead_count_total = lead_count_result['total'] if lead_count_result else 0
    
    # Check if first lead is recent (within 24 hours)
    is_first_lead_recent = False
    if lead_count_total == 1 and leads:
        from datetime import datetime, timedelta
        first_lead = leads[0]
        if first_lead.get('created_at'):
            lead_time = first_lead['created_at']
            if hasattr(lead_time, 'tzinfo'):
                # Handle timezone-aware datetime
                from datetime import timezone
                now = datetime.now(timezone.utc)
            else:
                now = datetime.now()
            is_first_lead_recent = (now - lead_time) < timedelta(hours=24)
    
    has_any_activity = metrics.get('total_scans', 0) > 0 or metrics.get('total_views', 0) > 0
    
    # First unassigned SmartSign ID (for "Assign SmartSign" button)
    first_unassigned_sign_id = None
    for a in sign_assets:
        if not a.get('active_property_id'):
            first_unassigned_sign_id = a['id']
            break

    return render_template(
        "dashboard.html",
        metrics=metrics,
        listings=listings_data,
        today_cards=today_cards,
        sign_assets=sign_assets,
        leads=leads,
        properties=properties,
        is_pro=current_user.is_pro,
        listing_signs=listing_signs,
        # Onboarding Activation (Phase 1)
        smart_sign_count=smart_sign_count,
        has_smartsigns=has_smartsigns,
        has_assigned_sign=has_assigned_sign,
        has_scan=has_scan,
        lead_count_total=lead_count_total,
        is_first_lead_recent=is_first_lead_recent,
        has_any_activity=has_any_activity,
        first_unassigned_sign_id=first_unassigned_sign_id,
        # Legacy compat
        has_assigned_smartsigns=has_assigned_sign,
    )


@dashboard_bp.route("/how-it-works")
@login_required
def how_it_works():
    """How SmartSigns Get Leads - tactical onboarding page."""
    return render_template("how_it_works.html", is_pro=current_user.is_pro)


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
        from utils.urls import normalize_https_url
        raw_tour = request.form.get("virtual_tour_url", "")
        virtual_tour_url = normalize_https_url(raw_tour)
        
        if raw_tour and not virtual_tour_url:
             flash("Invalid Virtual Tour URL. Must be HTTPS.", "error")
             # Do not save invalid URL, keep old one? Or just nullify? 
             # Safe default: redirect back to fix
             return redirect(url_for('dashboard.edit_property', property_id=property_id))

        db.execute('''
            UPDATE properties 
            SET address = %s, beds = %s, baths = %s, sqft = %s, price = %s, description = %s, virtual_tour_url = %s
            WHERE id = %s
        ''', (address, beds, baths, sqft, price, description, virtual_tour_url, property_id))

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


@dashboard_bp.route("/dashboard/properties/<int:property_id>/analytics")
@login_required
def property_analytics(property_id):
    """
    Detailed analytics page for a single property.
    """
    db = get_db()
    from services.analytics import per_property_metrics
    from flask import abort
    
    # Verify ownership
    property_row = db.execute(
        "SELECT * FROM properties WHERE id = %s AND agent_id IN (SELECT id FROM agents WHERE user_id = %s)",
        (property_id, current_user.id)
    ).fetchone()
    
    if not property_row:
        return abort(404)
        
    metrics = per_property_metrics(property_id, range_days=7)
    
    return render_template("dashboard/property_analytics.html", property=property_row, analytics=metrics)

@dashboard_bp.route("/dashboard/today")
@login_required
def today():
    """
    'Today' Action Feed.
    Highlights actionable items:
    - Zero Scans (7d)
    - Momentum (>50% Scan Growth)
    - High Intent (CTA but no Lead)
    """
    db = get_db()
    from services.analytics import per_property_metrics
    
    agent_id = db.execute("SELECT id FROM agents WHERE user_id = %s", (current_user.id,)).fetchone()
    if not agent_id:
        return render_template("dashboard/today.html", cards=[])
        
    properties = db.execute("SELECT id, address, slug FROM properties WHERE agent_id = %s", (agent_id['id'],)).fetchall()
    
    cards = []
    
    for p in properties:
        pm = per_property_metrics(p['id'], range_days=7)
        
        # 1. Zero Scans
        if pm['scans']['total'] == 0:
            cards.append({
                'type': 'warning',
                'title': 'Zero Visibility',
                'message': f"{p['address']} has 0 scans in the last 7 days.",
                'action': 'Check Sign Placement',
                'link': url_for('properties.property_page', slug=p['slug'])
            })
            
        # 2. Momentum
        if pm['scans']['delta'] > 50 and pm['scans']['total'] > 5:
            cards.append({
                'type': 'success',
                'title': 'Gaining Momentum',
                'message': f"{p['address']} scans up {pm['scans']['delta']}% WoW!",
                'action': 'View Analytics',
                'link': url_for('dashboard.property_analytics', property_id=p['id'])
            })
            
        # 3. High Intent (CTA > 0, Leads = 0)
        if pm['ctas']['total'] > 0 and pm['leads']['total'] == 0:
             cards.append({
                'type': 'info',
                'title': 'High Intent, No Leads',
                'message': f"{p['address']} has {pm['ctas']['total']} engagements but no leads.",
                'action': 'Review Pricing/Photos',
                'link': url_for('dashboard.edit_property', property_id=p['id'])
            })
            
    return render_template("dashboard/today.html", cards=cards)


# =============================================================================
# SmartSigns Management (MVP)
# =============================================================================



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
