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
from utils.uploads import save_image_upload
from utils.storage import get_storage
from slugify import slugify
from utils.qr_codes import generate_unique_code
from utils.timestamps import utc_iso
from services.gating import can_create_property
from constants import PAID_STATUSES
from datetime import datetime, timezone, timedelta
from services.subscriptions import is_subscription_active

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
    from services.analytics import per_agent_rollup, per_property_metrics, get_agent_lead_timeseries

    # 1. Main Metrics Rollup
    metrics = per_agent_rollup(current_user.id)

    # 2. Determine all agent IDs linked to this user (supports multiple agent rows)
    agent_rows = db.execute(
        "SELECT id FROM agents WHERE user_id = %s",
        (current_user.id,)
    ).fetchall()
    agent_ids = [r['id'] for r in agent_rows] if agent_rows else []
    agent_ids_param = agent_ids if agent_ids else [-1]  # Safe sentinel

    # --- PRE-FETCH SIGN DATA (Moved up for Sign Type logic) ---

    # 5. SmartSigns (Legacy/MVP Compat) with Performance Metrics
    from services.smart_signs import SmartSignsService
    sign_assets_rows = SmartSignsService.get_user_assets(current_user.id)
    # Convert to mutable dicts to allow adding proper metrics
    sign_assets = [dict(row) for row in sign_assets_rows]
    
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
    
    # Enrich sign_assets with metrics AND build map for properties
    smart_sign_map = set() # Set of property IDs with assigned SmartSigns

    for asset in sign_assets:
        aid = asset['id']
        scans = scans_by_asset.get(aid, 0)
        leads = leads_by_asset.get(aid, 0)
        asset['scans'] = scans
        asset['leads'] = leads
        asset['is_pending_order'] = False # Default Flag
        
        # Conversion rate: show "—" if insufficient data
        if scans < 5:
            asset['conversion'] = "—"
        else:
            conv = (leads / scans) * 100
            asset['conversion'] = f"{conv:.1f}%"
            
        if asset.get('active_property_id'):
            smart_sign_map.add(asset['active_property_id'])

    # 5c. [FIX] Append Pending SmartSign Orders (Unpaid)
    # These do not have assets yet, but should be visible to resume.
    pending_smart_orders = db.execute("""
        SELECT id, created_at, design_payload as payload
        FROM orders
        WHERE user_id = %s 
          AND order_type = 'smart_sign'
          AND status = 'pending_payment'
        ORDER BY created_at DESC
    """, (current_user.id,)).fetchall()

    for po in pending_smart_orders:
        # Create a mock asset object
        # Try to extract name from payload if possible
        import json
        label = "Draft Verification Sign"
        try:
             # payload is often dict in compiled SQL, but check type
             pl = po['payload']
             if isinstance(pl, str):
                 pl = json.loads(pl)
             if pl and 'agent_name' in pl:
                 label = f"Draft: {pl['agent_name']}"
        except:
             pass

        sign_assets.insert(0, {
            'id': po['id'], # Use ORDER ID here, template must handle this!
            'label': label,
            'code': '—',
            'active_property_id': None,
            'property_address': None,
            'is_frozen': False,
            'activated_at': None,
            'scans': 0,
            'leads': 0,
            'conversion': '—',
            'is_pending_order': True
        })

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
          AND o.status = ANY(%s)
        ORDER BY o.created_at DESC
        """,
        (current_user.id, list(PAID_STATUSES))
    ).fetchall()
    
    # Enrich with status labels for display AND build map
    listing_signs = []
    yard_sign_map = set() # Set of property IDs with yard signs

    for row in listing_signs_raw:
        from services.gating import get_property_gating_status
        gating = get_property_gating_status(row['id'])
        
        if gating['is_expired'] and not gating['is_paid']:
            status_label = 'Expired'
            status_color = 'expired'
        elif gating['is_paid']:
            status_label = 'Active'
            status_color = 'active'
            yard_sign_map.add(row['id'])
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
            
            # Determine Sign Type
            sign_types = []
            if p['id'] in smart_sign_map:
                sign_types.append("SmartSign")
            if p['id'] in yard_sign_map:
                sign_types.append("Yard Sign")
            
            sign_type_str = ", ".join(sign_types) if sign_types else "—"

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
                "sign_type": sign_type_str
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

    # 8. Onboarding Activation (Phase 1 Sprint)
    # Compute all flags server-side for template simplicity
    from datetime import datetime, timedelta, timezone
    
    smart_sign_count = len(sign_assets)
    has_smartsigns = smart_sign_count > 0
    
    # Count assigned vs unassigned SmartSigns
    assigned_sign_count = sum(1 for a in sign_assets if a.get('active_property_id'))
    has_assigned_sign = assigned_sign_count > 0
    
    # Scan counts and first scan detection
    scan_count_total = 0
    has_scan = False
    is_first_scan_recent = False
    latest_scan_at = None
    
    if has_smartsigns:
        scan_stats = db.execute("""
            SELECT COUNT(*) as count, MAX(scanned_at) as latest
            FROM qr_scans 
            WHERE sign_asset_id = ANY(%s)
        """, (asset_ids,)).fetchone()
        scan_count_total = scan_stats['count'] or 0
        has_scan = scan_count_total > 0
        latest_scan_at = scan_stats['latest']
        
        # Check if first scan is recent (within 24 hours and exactly 1 scan)
        if scan_count_total == 1 and latest_scan_at:
            if hasattr(latest_scan_at, 'tzinfo') and latest_scan_at.tzinfo:
                now = datetime.now(timezone.utc)
            else:
                now = datetime.now()
            is_first_scan_recent = (now - latest_scan_at) < timedelta(hours=24)
    
    # Lead counts and first lead detection
    lead_stats = db.execute("""
        SELECT COUNT(*) as total, MAX(l.created_at) as latest
        FROM leads l
        JOIN properties p ON l.property_id = p.id
        WHERE p.agent_id = ANY(%s)
    """, (agent_ids_param,)).fetchone()
    lead_count_total = lead_stats['total'] or 0
    latest_lead_at = lead_stats['latest']
    
    # Check if first lead is recent (within 24 hours)
    is_first_lead_recent = False
    if lead_count_total == 1 and latest_lead_at:
        if hasattr(latest_lead_at, 'tzinfo') and latest_lead_at.tzinfo:
            now = datetime.now(timezone.utc)
        else:
            now = datetime.now()
        is_first_lead_recent = (now - latest_lead_at) < timedelta(hours=24)
    
    # Dashboard Mode: determines overall state
    # - "no_signs": hard gate, user has 0 SmartSigns
    # - "needs_assignment": semi-hard gate, has SmartSigns but none assigned
    # - "active": normal dashboard
    if smart_sign_count == 0:
        dashboard_mode = "no_signs"
    elif assigned_sign_count == 0:
        dashboard_mode = "needs_assignment"
    else:
        dashboard_mode = "active"
    
    # Progress percent for progress bar
    # 0% = no sign, 25% = has sign, 50% = assigned, 75% = has scan, 100% = has lead
    if lead_count_total > 0:
        progress_percent = 100
    elif has_scan:
        progress_percent = 75
    elif has_assigned_sign:
        progress_percent = 50
    elif has_smartsigns:
        progress_percent = 25
    else:
        progress_percent = 0
    
    # First unassigned SmartSign ID (for "Assign SmartSign" button) - computed before next_step
    first_unassigned_sign_id = None
    for a in sign_assets:
        if not a.get('active_property_id'):
            first_unassigned_sign_id = a['id']
            break
    
    # Next step label and CTA for progress bar
    if not has_smartsigns:
        next_step_label = "Create your first SmartSign"
        next_step_cta = "Create SmartSign"
        next_step_url = url_for('smart_signs.order_start')
    elif not has_assigned_sign:
        next_step_label = "Assign your SmartSign to a property"
        next_step_cta = "Assign SmartSign"
        if first_unassigned_sign_id:
            next_step_url = url_for('dashboard.index', highlight_asset_id=first_unassigned_sign_id) + '#smart-signs-section'
        else:
            next_step_url = url_for('dashboard.index') + '#smart-signs-section'
    elif not has_scan:
        next_step_label = "Place the sign and test-scan it"
        next_step_cta = "View Property Page"
        # Find first assigned property
        first_assigned_property = None
        for a in sign_assets:
            if a.get('active_property_id'):
                prop = db.execute("SELECT slug FROM properties WHERE id = %s", (a['active_property_id'],)).fetchone()
                if prop:
                    first_assigned_property = prop['slug']
                    break
        next_step_url = url_for('properties.property_page', slug=first_assigned_property) if first_assigned_property else None
    else:
        next_step_label = "Wait for a buyer inquiry (or test the form)"
        next_step_cta = "View Leads"
        next_step_url = url_for('dashboard.index') + '#leads-section'
    
    # has_any_activity: True if any lifetime metrics are non-zero
    has_any_activity = (
        metrics.get('scans', {}).get('lifetime', 0) > 0 or
        metrics.get('views', {}).get('lifetime', 0) > 0 or
        metrics.get('leads', {}).get('lifetime', 0) > 0 or
        metrics.get('ctas', {}).get('7d', 0) > 0
    )
    
    # 9. New User Detection (for enhanced onboarding)
    # True if user has 0 properties AND 0 SmartSigns
    property_count = len(properties)
    is_new_user = (property_count == 0 and smart_sign_count == 0)

    # 10. Chart Data (Lead Timeseries)
    chart_data = get_agent_lead_timeseries(current_user.id, days=30)

    return render_template(
        "dashboard.html",
        metrics=metrics,
        chart_data=chart_data,
        listings=listings_data,
        today_cards=today_cards,
        sign_assets=sign_assets,
        leads=leads,
        properties=properties,
        is_pro=current_user.is_pro,
        listing_signs=listing_signs,
        # Onboarding Activation (Phase 1 Sprint)
        dashboard_mode=dashboard_mode,
        smart_sign_count=smart_sign_count,
        assigned_sign_count=assigned_sign_count,
        has_smartsigns=has_smartsigns,
        has_assigned_sign=has_assigned_sign,
        has_scan=has_scan,
        scan_count_total=scan_count_total,
        is_first_scan_recent=is_first_scan_recent,
        lead_count_total=lead_count_total,
        is_first_lead_recent=is_first_lead_recent,
        progress_percent=progress_percent,
        next_step_label=next_step_label,
        next_step_cta=next_step_cta,
        next_step_url=next_step_url,
        has_any_activity=has_any_activity,
        first_unassigned_sign_id=first_unassigned_sign_id,
        is_new_user=is_new_user,
        property_count=property_count,
        # Legacy compat
        has_assigned_smartsigns=has_assigned_sign,
        highlight_asset_id=request.args.get("highlight_asset_id", type=int),
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


@dashboard_bp.route("/properties/<int:property_id>/analytics")
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

@dashboard_bp.route("/today")
@login_required
def today():
    # 'Today' Action Feed.
    # Highlights actionable items:
    # - Zero Scans (7d)
    # - Momentum (>50% Scan Growth)
    # - High Intent (CTA but no Lead)
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
# Legacy Redirects (Fixing route prefixes)
# =============================================================================

@dashboard_bp.route("/dashboard/today")
@login_required
def legacy_today():
    return redirect(url_for('dashboard.today'), code=301)

@dashboard_bp.route("/dashboard/properties/<int:property_id>/analytics")
@login_required
def legacy_property_analytics(property_id):
    return redirect(url_for('dashboard.property_analytics', property_id=property_id), code=301)


# =============================================================================
# Kits
# =============================================================================

@dashboard_bp.route("/kits")
@login_required
def kits():
    """
    Kits Management Page.
    Lists properties and their kit status.
    """
    db = get_db()
    # Query properties for current user with LEFT JOIN listing_kits to get kit_id + kit_status
    properties = db.execute(
        """
        SELECT p.id, p.address, lk.id as kit_id, lk.status as kit_status
        FROM properties p
        JOIN agents a ON p.agent_id = a.id
        LEFT JOIN listing_kits lk ON lk.property_id = p.id
        WHERE a.user_id = %s
        ORDER BY p.created_at DESC
        """,
        (current_user.id,)
    ).fetchall()
    
    return render_template("dashboard/kits.html", properties=properties)


# =============================================================================
# SmartSigns Management (MVP)
# =============================================================================



@dashboard_bp.route("/smart-signs/<int:asset_id>/assign", methods=["POST"])
@login_required
def assign_smart_sign(asset_id):
    """
    Assign or Reassign a SmartSign.
    Entitlements are enforced by SmartSignsService.assign_asset.
    """
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
    
    try:
        SmartSignsService.assign_asset(asset_id, property_id, current_user.id)
        flash("SmartSign assignment updated.", "success")
    except ValueError as e:
        # Business logic errors (frozen, not activated, etc)
        flash(str(e), "error")
    except PermissionError as e:
        # Upgrade required for reassign/unassign
        flash(f"{e}", "error") # Message already contains "Upgrade required"
    except Exception as e:
        flash("Error assigning SmartSign.", "error")
        print(f"[SmartSigns] Assign Error: {e}")
        
    return redirect(url_for('dashboard.index', _anchor='smart-signs-section'))

@dashboard_bp.route("/properties/new", methods=["GET", "POST"])
@login_required
def new_property():
    """
    Free Property Creation Flow.
    Separated from listing sign purchase flow.
    """
    if request.method == "POST":
        db = get_db()
        
        # 0. Check Limits
        is_pro = is_subscription_active(current_user.subscription_status)
        
        if not is_pro:
            gating = can_create_property(current_user.id)
            if not gating['allowed']:
                flash(f"Free limit reached ({gating['limit']} listings). Upgrade to Pro.", "error")
                return redirect(url_for('dashboard.new_property'))

        # Fetch Agent ID
        agent = db.execute("SELECT id FROM agents WHERE user_id = %s", (current_user.id,)).fetchone()
        if not agent:
            # Create Default Agent Profile if missing (required for property)
            cursor = db.cursor()
            cursor.execute(
                "INSERT INTO agents (user_id, name, email) VALUES (%s, %s, %s) RETURNING id",
                (current_user.id, current_user.display_name, current_user.email)
            )
            agent_id = cursor.fetchone()['id']
            db.commit()
        else:
            agent_id = agent['id']
            
        # Parse Form
        address = request.form.get('address')
        beds = request.form.get('beds')
        baths = request.form.get('baths')
        price = request.form.get('price')
        
        # Optional URLs
        from utils.urls import normalize_https_url
        raw_scheduling = request.form.get('scheduling_url', '')
        scheduling_url = normalize_https_url(raw_scheduling) if raw_scheduling else None
        
        raw_virtual_tour = request.form.get('virtual_tour_url', '')
        virtual_tour_url = normalize_https_url(raw_virtual_tour) if raw_virtual_tour else None
        
        # Update agent's scheduling_url if provided
        if scheduling_url:
            db.execute("UPDATE agents SET scheduling_url = %s WHERE id = %s", (scheduling_url, agent_id))
        
        # Expiry logic
        expires_at = None
        if not is_pro:
             retention = int(os.environ.get("FREE_TIER_RETENTION_DAYS", "7"))
             expires_at = (datetime.now(timezone.utc) + timedelta(days=retention)).isoformat(sep=' ')
             
        cursor = db.cursor()
        cursor.execute("""
            INSERT INTO properties (agent_id, address, beds, baths, price, virtual_tour_url, created_at, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (agent_id, address, beds, baths, price, virtual_tour_url, utc_iso(), expires_at))
        pid = cursor.fetchone()['id']
        
        # Slug & QR
        base_slug = slugify(address)
        slug = base_slug
        ctr = 2
        while db.execute("SELECT 1 FROM properties WHERE slug=%s", (slug,)).fetchone():
            slug = f"{base_slug}-{ctr}"
            ctr += 1
        cursor.execute("UPDATE properties SET slug=%s WHERE id=%s", (slug, pid))
        
        code = generate_unique_code(db, length=12)
        cursor.execute("UPDATE properties SET qr_code=%s WHERE id=%s", (code, pid))

        # Handle Photo Uploads
        if 'property_photos' in request.files:
            photos = request.files.getlist('property_photos')
            valid_photos = [p for p in photos if p and p.filename != '']
            
            if valid_photos:
                # Basic Limit Check (simpler than edit flow)
                max_photos = 1 if not is_pro else 20
                if len(valid_photos) > max_photos:
                    flash(f"Limit reached: You can only upload {max_photos} photo(s). Upgrade for more.", "warning")
                    valid_photos = valid_photos[:max_photos]

                for photo in valid_photos:
                    try:
                        base_name = f"property_{pid}"
                        safe_key = save_image_upload(
                            photo,
                            PROPERTY_PHOTOS_KEY_PREFIX,
                            base_name,
                            validate_image=True
                        )
                        cursor.execute(
                            "INSERT INTO property_photos (property_id, filename) VALUES (%s, %s)", 
                            (pid, safe_key)
                        )
                    except Exception as e:
                        print(f"Error saving photo: {e}")
                        # Continue saving others

        db.commit()
        
        flash("Property created successfully.", "success")
        
        # Redirect to success page with SmartSign CTA
        return redirect(url_for('dashboard.property_created', property_id=pid))
        
    return render_template("dashboard/property_new.html")


@dashboard_bp.route("/properties/<int:property_id>/success")
@login_required
def property_created(property_id):
    """
    Success page after property creation.
    Prompts user to order a SmartSign for the new property.
    """
    db = get_db()
    
    # Verify ownership
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
        flash("Property not found.", "error")
        return redirect(url_for('dashboard.index'))
    
    # Check for unassigned SmartSigns
    unassigned_sign = db.execute("""
        SELECT id FROM sign_assets 
        WHERE user_id = %s AND active_property_id IS NULL
        ORDER BY created_at ASC LIMIT 1
    """, (current_user.id,)).fetchone()
    
    return render_template(
        "dashboard/property_created.html",
        property=property_row,
        has_unassigned_sign=bool(unassigned_sign),
        first_unassigned_sign_id=unassigned_sign['id'] if unassigned_sign else None
    )


