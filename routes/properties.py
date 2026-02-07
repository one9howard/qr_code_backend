"""
Property Page Routes with Separate QR Scan and Page View Analytics.

Routes:
- GET /p/<slug> - Canonical property page (logs page views, NOT scans)
- GET /r/<code> - QR scan entrypoint (logs scan, redirects to /p/<slug>)
- GET /go/<property_id> - Internal agent redirect (sets cookie, redirects)
"""
import hashlib
import os
import secrets
from datetime import date
from flask import Blueprint, render_template, abort, request, redirect, url_for, make_response
from flask_login import login_required, current_user
from database import get_db
from config import IS_PRODUCTION

properties_bp = Blueprint('properties', __name__)

# Cookie settings
INTERNAL_VIEW_COOKIE = 'internal_view'
INTERNAL_VIEW_MAX_AGE = 1800  # 30 minutes
SMART_ATTRIB_COOKIE = 'smart_attrib'
SMART_ATTRIB_MAX_AGE = 7 * 24 * 3600  # 7 days


def compute_visitor_hash(ip, user_agent):
    """
    Compute a privacy-conscious visitor hash.
    Uses daily salt so hashes rotate and don't enable permanent tracking.
    """
    from flask import current_app
    server_secret = current_app.config['SECRET_KEY']
    if not server_secret:
        raise ValueError("SECRET_KEY must be configured for visitor hashing.")
        
    daily_salt = f"{date.today().isoformat()}-{server_secret}"
    raw = f"{ip}|{user_agent}|{daily_salt}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def generate_qr_code() -> str:
    """Generate a unique 12-char URL-safe shortcode for QR URLs.
    
    Single source of truth: utils/qr_codes.generate_unique_code
    """
    from utils.qr_codes import generate_unique_code
    return generate_unique_code(get_db(), length=12)


# =============================================================================
# QR Scan Entrypoint: /r/<code>
# =============================================================================

@properties_bp.route("/r/<code>")
def qr_scan_redirect(code):
    """
    QR scan entrypoint - logs scan and redirects to property page.
    Supports both:
    1. QR Variants (from qr_variants table)
    2. Legacy Property Shortcodes (fallback)
    """
    db = get_db()
    
    # 0. Check SmartSigns (Phase 1 MVP)
    from services.smart_signs import SmartSignsService
    asset, asset_property_row = SmartSignsService.resolve_asset(code)

    if asset:
        # SmartSign Found - Check activation status (Option B)
        if asset['activated_at'] is None:
            # Not activated - must purchase SmartSign to activate
            return render_template("sign_asset_not_activated.html", asset=asset)
        
        if not asset_property_row:
            # Unassigned -> Log scan via app_events and Render Unassigned Page
            # Using app_events (Option 2) avoids qr_scans.property_id NOT NULL constraint
            try:
                from services.events import track_event
                track_event(
                    "smart_sign_scan",
                    source="server",
                    sign_asset_id=asset['id'],
                    payload={
                        "scan_type": "unassigned",
                        "asset_code": asset['code']
                    }
                )
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"[Analytics] Error logging unassigned SmartSign scan: {e}", exc_info=True)
            
            return render_template("sign_asset_unassigned.html", asset=asset)
        
        # Assigned -> Proceed to setup redirect
        property_id = asset_property_row['id']
        property_row = asset_property_row
        
        # Explicit sign_asset_id for logging
        sign_asset_id = asset['id']
        
        # Pre-fill variant/campaign as None (mutually exclusive with SmartSigns for now)
        campaign_id = None
        variant_id = None
        
    else:
        # Fallback: Legacy Logic
        sign_asset_id = None # Not a SmartSign

        # 1. Check QR Variants first (Phase 2)
        variant = db.execute("""
            SELECT v.id as variant_id, v.property_id, v.campaign_id, c.name as campaign_name
            FROM qr_variants v
            LEFT JOIN campaigns c ON v.campaign_id = c.id
            WHERE v.code = %s
        """, (code,)).fetchone()
        
        property_id = None
        campaign_id = None
        variant_id = None
        
        if variant:
            # Found a variant
            property_id = variant['property_id']
            campaign_id = variant['campaign_id']
            variant_id = variant['variant_id']
            
            # Fetch property details needed for redirect and gating check
            property_row = db.execute(
                """SELECT p.*, a.name as agent_name, a.brokerage 
                   FROM properties p
                   JOIN agents a ON p.agent_id = a.id
                   WHERE p.id = %s""", 
                (property_id,)
            ).fetchone()
            
        else:
            # Fallback to Legacy Property Code
            property_row = db.execute(
                """SELECT p.*, a.name as agent_name, a.brokerage, a.email as agent_email, 
                   a.phone as agent_phone, a.photo_filename as agent_photo
                   FROM properties p
                   JOIN agents a ON p.agent_id = a.id
                   WHERE p.qr_code = %s""",
                (code,)
            ).fetchone()
            
            if property_row:
                property_id = property_row['id']
    
    if not property_row:
        abort(404)
    
    # 2. Gating Check: Stop Counting Scans for Expired Listings
    from services.gating import get_property_gating_status
    gating = get_property_gating_status(property_id)
    
    if gating['is_expired'] and not gating['is_paid']:
        # Return 410 Gone (do not insert scan)
        return render_template(
            "property_expired.html",
            property=property_row, 
            gating=gating
        ), 410
    
    # 3. Log QR scan
    try:
        from utils.net import get_client_ip
        ip_address = get_client_ip()
        user_agent = request.headers.get('User-Agent', '')[:500]
        utm_source = request.args.get('utm_source', '')[:100]
        utm_medium = request.args.get('utm_medium', '')[:100]
        utm_campaign = request.args.get('utm_campaign', '')[:100]
        referrer = (request.referrer or '')[:500]
        visitor_hash = compute_visitor_hash(ip_address, user_agent)
        
        db.execute(
            """INSERT INTO qr_scans 
               (property_id, ip_address, user_agent, utm_source, utm_medium, 
                utm_campaign, referrer, visitor_hash, qr_variant_id, campaign_id, sign_asset_id) 
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (property_id, ip_address, user_agent, utm_source or None, 
             utm_medium or None, utm_campaign or None, referrer or None, 
             visitor_hash, variant_id, campaign_id, sign_asset_id)
        )
        db.commit()
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"[Analytics] Error logging QR scan: {e}", exc_info=True)
    
    # Create redirect response
    response = make_response(
        redirect(url_for('properties.property_page', slug=property_row['slug']))
    )
    
    # Set signed attribution cookie ONLY for assigned SmartSign assets
    if sign_asset_id:
        import time
        from utils.attrib import make_attrib_token
        from config import SECRET_KEY
        
        token = make_attrib_token(sign_asset_id, int(time.time()), SECRET_KEY)
        response.set_cookie(
            SMART_ATTRIB_COOKIE,
            token,
            max_age=SMART_ATTRIB_MAX_AGE,
            httponly=True,
            samesite='Lax',
            secure=IS_PRODUCTION,
            path='/'
        )
    
    return response


# =============================================================================
# Internal Agent Redirect: /go/<property_id>
# =============================================================================

@properties_bp.route("/go/<int:property_id>")
@login_required
def internal_agent_redirect(property_id):
    """
    Internal agent redirect - sets cookie and redirects to property page.
    
    Used for dashboard/assets links so agent views don't inflate buyer analytics.
    Requires login and property ownership.
    """
    db = get_db()
    
    # Verify ownership: property must belong to ANY agent linked to current user
    property_row = db.execute(
        """
        SELECT p.slug 
        FROM properties p
        JOIN agents a ON p.agent_id = a.id
        WHERE p.id = %s AND a.user_id = %s
        """,
        (property_id, current_user.id)
    ).fetchone()
    
    if not property_row:
        abort(403)  # Not owner or property not found
    
    # Create response with redirect
    response = make_response(
        redirect(url_for('properties.property_page', slug=property_row['slug']))
    )
    
    # Set internal view cookie
    response.set_cookie(
        INTERNAL_VIEW_COOKIE,
        '1',
        max_age=INTERNAL_VIEW_MAX_AGE,
        httponly=True,
        samesite='Lax',
        secure=IS_PRODUCTION
    )
    
    return response


# =============================================================================
# Canonical Property Page: /p/<slug>
# =============================================================================

@properties_bp.route("/p/<slug>")
def property_page(slug):
    """
    Display property page and log page view (NOT QR scan).
    
    QR scans are logged ONLY through /r/<code>.
    Page views track all visitors to /p/<slug>.
    """
    db = get_db()
    
    property_row = None
    
    # Find by canonical slug
    property_row = db.execute(
        """SELECT p.*, a.name as agent_name, a.brokerage, a.email as agent_email, 
           a.phone as agent_phone, a.photo_filename as agent_photo, a.user_id as agent_user_id, 
           a.scheduling_url as agent_scheduling_url 
           FROM properties p 
           JOIN agents a ON p.agent_id = a.id 
           WHERE p.slug = %s""",
        (slug,)
    ).fetchone()
    
    # Fallback: legacy ID-based slug format (e.g., "123-property-name")
    if not property_row:
        try:
            property_id = int(slug.split('-')[0])
            property_row = db.execute(
                """SELECT p.*, a.name as agent_name, a.brokerage, a.email as agent_email, 
                   a.phone as agent_phone, a.photo_filename as agent_photo, a.user_id as agent_user_id, 
                   a.scheduling_url as agent_scheduling_url 
                   FROM properties p 
                   JOIN agents a ON p.agent_id = a.id 
                   WHERE p.id = %s""",
                (property_id,)
            ).fetchone()
            
            # Redirect to canonical URL if found
            if property_row and property_row['slug']:
                return redirect(
                    url_for('properties.property_page', slug=property_row['slug']),
                    code=301
                )
        except (ValueError, IndexError):
            pass
    
    if not property_row:
        abort(404)
    
    property_id = property_row['id']
    
    # --- Gating Check (Single Source of Truth) ---
    from services.gating import get_property_gating_status
    gating = get_property_gating_status(property_id)
    
    # Determine Tier State
    tier_state = "FREE"
    if gating.get('is_paid'):
        tier_state = "PAID"
    elif gating.get('is_expired'):
        tier_state = "EXPIRED"
    else:
        # Default fallback
        pass

    # --- Log Page View (NOT scan) ---
    try:
        from utils.net import get_client_ip
        from services.events import track_event
        
        ip_address = get_client_ip()
        user_agent = request.headers.get('User-Agent', '')[:500]
        referrer = (request.referrer or '')[:500]
        
        # Check for internal view (Cookie AND Ownership Backstop)
        is_internal_bool = False
        
        # 1. Cookie Check (Fast Path)
        if request.cookies.get(INTERNAL_VIEW_COOKIE) == '1':
            is_internal_bool = True
            
        # 2. Ownership Check (Backstop)
        # If logged in and owning the property, it is ALWAYS internal.
        if not is_internal_bool and current_user.is_authenticated:
            if property_row['agent_user_id'] == current_user.id:
                is_internal_bool = True
        
        # Store as integer for database compatibility
        is_internal = 1 if is_internal_bool else 0
        source = 'dashboard' if is_internal_bool else 'public'
        
        # 1. Legacy Logging (wrapped in its own try/except to prevent poisoning)
        try:
            db.execute(
                """INSERT INTO property_views 
                   (property_id, ip_address, user_agent, referrer, is_internal, source) 
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (property_id, ip_address, user_agent, referrer or None, is_internal, source)
            )
            db.commit()
        except Exception as db_err:
            db.rollback()
            import logging
            logging.getLogger(__name__).exception(f"[Analytics] DB error logging page view: {db_err}")
        
        # 2. Canonical App Event
        track_event(
            "property_view",
            source="server",
            property_id=property_id,
            user_id=property_row['agent_user_id'], # The agent who owns the property
            qr_code=property_row.get('qr_code'),
            payload={
                "tier_state": tier_state,
                "referrer": referrer,
                "utm_source": request.args.get('utm_source'),
                "utm_medium": request.args.get('utm_medium'),
                "is_mobile": "Mobile" in user_agent,
                "is_internal": bool(is_internal_bool)
            }
        )
        
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"[Analytics] Error logging page view: {e}", exc_info=True)
    
    # Expired and unpaid -> 410 Gone
    if gating['is_expired'] and not gating['is_paid']:
        return render_template(
            "property_expired.html",
            property=property_row,
            gating=gating
        ), 410

    # Fetch Photos
    # IMPORTANT: In FREE/EXPIRED states, we must NOT generate or render real photo URLs.
    # We can still compute a count for upsell copy.
    total_photos_row = db.execute(
        'SELECT COUNT(*) AS c FROM property_photos WHERE property_id = %s',
        (property_id,)
    ).fetchone()
    photo_count_total = int(total_photos_row['c']) if total_photos_row and total_photos_row.get('c') is not None else 0

    photo_urls = []
    if gating.get('is_paid') and photo_count_total > 0:
        # Paid: we are allowed to generate URLs
        limit_clause = f"LIMIT {gating.get('max_photos', 50)}"
        photo_rows = db.execute(
            f'SELECT filename FROM property_photos WHERE property_id = %s {limit_clause}',
            (property_id,)
        ).fetchall()
        from utils.template_helpers import get_storage_url
        photo_urls = [get_storage_url(r['filename']) for r in photo_rows]

    # Property data for client-side JS (safe JSON injection in template)
    tier_state = 'paid' if gating.get('is_paid') else ('expired' if gating.get('is_expired') else 'free')
    property_data = {
        'id': property_id,
        'tier': tier_state,
        'photos': photo_urls,
        'photoCountTotal': photo_count_total,
        'agentName': property_row.get('agent_name')
    }

    # Check for Open House Mode
    open_house_mode = request.args.get('mode') == 'open_house'

    return render_template(
        "property.html", 
        property=property_row, 
        photo_urls=photo_urls,
        photo_count_total=photo_count_total,
        property_data=property_data,
        gating=gating,
        open_house_mode=open_house_mode
    )
