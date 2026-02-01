"""
Leads Blueprint - Buyer Lead Capture for Agents.

Provides:
- POST /api/leads/submit - Submit a lead request from property page
- GET /api/leads/export.csv - Export leads as CSV (Pro only)

CSRF Configuration:
    This blueprint is EXEMPT from CSRF protection (configured in app.py).
    
    Rationale (Option A - Public Form Exemption):
    - /api/leads/submit is a public-facing endpoint for anonymous buyers
    - Protected by: honeypot field, IP-based rate limiting (5/hour), 
      consent checkbox, and server-side validation
    - CORS is not permissive (default Flask behavior)
    
    Alternative (Option B):
    - Would require adding CSRF token to property.html for anonymous users
    - More complex for a public lead form with minimal benefit
"""
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, current_app
from database import get_db
from utils.timestamps import minutes_ago, utc_now

leads_bp = Blueprint('leads', __name__)

# Rate limiting: max 5 submissions per hour per IP
RATE_LIMIT_MAX = 5
RATE_LIMIT_WINDOW_MINUTES = 60


def check_rate_limit(ip_address: str) -> bool:
    """
    Check if IP has exceeded rate limit.
    Returns True if allowed, False if rate limited.
    """
    db = get_db()
    window_start = minutes_ago(RATE_LIMIT_WINDOW_MINUTES)
    
    count = db.execute(
        """SELECT COUNT(*) as cnt FROM leads 
           WHERE ip_address = %s AND created_at > %s""",
        (ip_address, window_start)
    ).fetchone()
    
    return count['cnt'] < RATE_LIMIT_MAX


@leads_bp.route("/api/leads/submit", methods=["POST"])
def submit_lead():
    """
    Submit a lead request from property page.
    
    Required fields: property_id, buyer_name, buyer_email, consent
    Optional fields: buyer_phone, preferred_contact, best_time, message
    
    Security:
    - Honeypot field check (reject if filled)
    - Rate limiting (5/hour per IP)
    - Consent checkbox required
    """
    db = get_db()
    
    # Use helper for ProxyFix compatibility
    from utils.net import get_client_ip
    ip_address = get_client_ip()
    
    # Get JSON data
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "No data provided"}), 400
    
    # Honeypot check - reject if filled (bot detection)
    if data.get("website"):  # Hidden honeypot field
        current_app.logger.warning(f"[Leads] Honeypot triggered from IP {ip_address}")
        # Return success to not alert bots, but don't save
        return jsonify({"success": True, "message": "Thank you for your request!"})
    
    # Rate limiting
    if not check_rate_limit(ip_address):
        current_app.logger.warning(f"[Leads] Rate limit exceeded for IP {ip_address}")
        return jsonify({
            "success": False, 
            "error": "rate_limited",
            "message": "Too many requests. Please try again later."
        }), 429
    
    # Validate required fields
    property_id = data.get("property_id")
    buyer_name = data.get("buyer_name", "").strip() or "Interested Buyer"  # Fallback if blank
    buyer_email = data.get("buyer_email", "").strip()
    buyer_phone = data.get("buyer_phone", "").strip()[:20] or None
    consent = data.get("consent")
    
    # --- Event Tracker Helper ---
    from services.events import track_event
    
    def track_lead_attempt(success, error=None, tier_state="unknown"):
        track_event(
            "lead_submitted",
            source="server",
            property_id=property_id if property_id else None,
            payload={
                "success": success,
                "error_code": error,
                "tier_state": tier_state,
                "honeypot_triggered": bool(data.get("website")),
                "lead_fields": {
                    "has_phone": bool(buyer_phone),
                    "has_email": bool(buyer_email),
                    "has_message": bool(data.get("message"))
                }
            }
        )

    if not property_id:
        track_lead_attempt(False, "missing_property_id")
        return jsonify({"success": False, "error": "Missing property_id"}), 400
    
    # Require at least one contact method: email OR phone
    if not buyer_email and not buyer_phone:
        track_lead_attempt(False, "missing_contact")
        return jsonify({"success": False, "error": "Email or phone is required"}), 400
    
    if not consent:
        track_lead_attempt(False, "missing_consent")
        return jsonify({"success": False, "error": "Consent is required"}), 400
    
    # Basic email validation (if provided)
    if buyer_email and ("@" not in buyer_email or "." not in buyer_email):
        track_lead_attempt(False, "invalid_email")
        return jsonify({"success": False, "error": "Invalid email address"}), 400
    
    # --- SmartSign Attribution (Signed Token) ---
    sign_asset_id = None
    lead_source = "direct"
    
    attrib_token = request.cookies.get("smart_attrib")
    if attrib_token:
        from utils.attrib import verify_attrib_token
        from config import SECRET_KEY
        
        verified_asset_id = verify_attrib_token(attrib_token, SECRET_KEY, max_age_seconds=7*24*3600)
        if verified_asset_id:
            # Confirm asset exists in DB
            asset_exists = db.execute(
                "SELECT id FROM sign_assets WHERE id = %s", (verified_asset_id,)
            ).fetchone()
            if asset_exists:
                sign_asset_id = verified_asset_id
                lead_source = "smart_sign"
    
    # Optional fields (buyer_phone already extracted above)
    preferred_contact = data.get("preferred_contact", "call")
    best_time = data.get("best_time", "").strip()[:50] or None
    message = data.get("message", "").strip()[:1000] or None
    
    # Validate preferred_contact
    if preferred_contact not in ("call", "text", "email"):
        preferred_contact = "call"
    
    # Lookup property and agent
    property_row = db.execute(
        "SELECT id, agent_id, address FROM properties WHERE id = %s",
        (property_id,)
    ).fetchone()
    
    if not property_row:
        track_lead_attempt(False, "property_not_found")
        return jsonify({"success": False, "error": "Property not found"}), 404
    
    # --- Expiry Check (Single Source of Truth) ---
    from services.gating import get_property_gating_status
    gating = get_property_gating_status(property_id)
    
    tier_state = "FREE"
    if gating.get('is_paid'): tier_state = "PAID"
    elif gating.get('is_expired'): tier_state = "EXPIRED"
    
    if gating['is_expired'] and not gating['is_paid']:
        current_app.logger.info(f"[Leads] Rejected lead for expired property {property_id}")
        track_lead_attempt(False, "expired", tier_state)
        return jsonify({
            "success": False,
            "error": "expired",
            "message": "This listing has expired. The agent can reactivate it by purchasing a sign."
        }), 410
    
    agent_id = property_row['agent_id']
    
    try:
        # Insert lead with attribution
        cursor = db.cursor()
        cursor.execute(
            """INSERT INTO leads 
               (property_id, agent_id, buyer_name, buyer_email, buyer_phone,
                preferred_contact, best_time, message, consent_given, ip_address,
                sign_asset_id, source)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               RETURNING id""",
            (property_id, agent_id, buyer_name, buyer_email or None, buyer_phone,
             preferred_contact, best_time, message, True, ip_address,
             sign_asset_id, lead_source)
        )
        lead_id = cursor.fetchone()['id']
        
        # --- Audit Log: Create notification record ---
        from utils.timestamps import utc_iso
        # RETURNING id required
        cursor.execute(
            """INSERT INTO lead_notifications (lead_id, channel, status, created_at)
               VALUES (%s, 'email', 'pending', %s)
               RETURNING id""",
            (lead_id, utc_iso())
        )
        notification_id = cursor.fetchone()['id']
        db.commit()
        
        current_app.logger.info(
            f"[Leads] New lead {lead_id} for property {property_id}"
        )
        
        # Track Success (Lead Submitted)
        track_lead_attempt(True, None, tier_state)
        
        # Send Notification (synchronous with audit update)
        from services.notifications import send_lead_notification_email
        agent_email = db.execute("SELECT email FROM agents WHERE id = %s", (agent_id,)).fetchone()['email']
        
        lead_payload = {
            "buyer_name": buyer_name,
            "buyer_email": buyer_email,
            "buyer_phone": buyer_phone,
            "property_address": property_row['address'],
            "message": message,
            "preferred_contact": preferred_contact,
            "best_time": best_time
        }
        
        success, error_msg, outcome_status = send_lead_notification_email(agent_email, lead_payload)
        
        # --- Audit Log: Update notification status ---
        event_status = "lead_notification_sent"
        
        if outcome_status == 'sent':
            db.execute(
                "UPDATE lead_notifications SET status = 'sent', sent_at = %s WHERE id = %s",
                (utc_iso(), notification_id)
            )
        else:
            # outcome_status is 'skipped' or 'failed'
            event_status = "lead_notification_failed"
            db.execute(
                "UPDATE lead_notifications SET status = %s, last_error = %s WHERE id = %s",
                (outcome_status, error_msg[:500] if error_msg else "Unknown error", notification_id)
            )
        db.commit()
        
        # Track Notification Event
        track_event(
            event_status,
            source="server",
            property_id=property_id,
            payload={
                "status": outcome_status,
                "provider": "email",
                "error_code": error_msg[:100] if error_msg else None
            }
        )
        
        # Build success response and clear attribution cookie
        from flask import make_response
        response = make_response(jsonify({
            "success": True,
            "message": "Thank you! The agent will contact you soon."
        }))
        
        # Clear attribution cookie after successful lead creation
        if sign_asset_id:
            response.set_cookie('smart_attrib', '', max_age=0, path='/')
        
        return response
        
    except Exception as e:
        current_app.logger.error(f"[Leads] Error saving lead: {e}")
        track_lead_attempt(False, "db_error", tier_state)
        return jsonify({
            "success": False, 
            "error": "Failed to submit request. Please try again."
        }), 500


# =============================================================================
# Pro-Tier CSV Export
# =============================================================================

@leads_bp.route("/api/leads/export.csv", methods=["GET"])
def export_leads_csv():
    """
    Export leads as CSV for Pro users.
    
    Security:
    - Requires login
    - Requires Pro subscription (active)
    - Only exports leads owned by the requesting agent
    
    Note: This route requires CSRF exemption (configured in app.py)
    since leads_bp is exempted for public lead submission.
    """
    from flask_login import current_user, login_required
    from flask import Response, abort
    from functools import wraps
    import csv
    import io
    from datetime import datetime
    
    # Manual login check since we can't use decorator inside function
    if not current_user.is_authenticated:
        return jsonify({"error": "Login required"}), 401
    
    # Pro subscription check
    if not current_user.is_pro:
        return jsonify({
            "error": "Pro subscription required",
            "message": "Upgrade to Pro to export your leads."
        }), 403
    
    db = get_db()
    
    # Get agent for current user
    agent = db.execute(
        "SELECT id FROM agents WHERE user_id = %s",
        (current_user.id,)
    ).fetchone()
    
    if not agent:
        return jsonify({"error": "Agent profile not found"}), 404
    
    # Fetch all leads for this agent
    leads = db.execute("""
        SELECT 
            l.created_at,
            p.address as property_address,
            l.buyer_name,
            l.buyer_email,
            l.buyer_phone,
            l.preferred_contact,
            l.best_time,
            l.message,
            l.status
        FROM leads l
        JOIN properties p ON l.property_id = p.id
        WHERE l.agent_id = %s
        ORDER BY l.created_at DESC
    """, (agent['id'],)).fetchall()
    
    # Build CSV
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Header row
    writer.writerow([
        'Date',
        'Property',
        'Buyer Name',
        'Buyer Email',
        'Buyer Phone',
        'Preferred Contact',
        'Best Time',
        'Message',
        'Status'
    ])
    
    # Data rows
    for lead in leads:
        writer.writerow([
            lead['created_at'] or '',
            lead['property_address'] or '',
            lead['buyer_name'] or '',
            lead['buyer_email'] or '',
            lead['buyer_phone'] or '',
            lead['preferred_contact'] or '',
            lead['best_time'] or '',
            lead['message'] or '',
            lead['status'] or ''
        ])
    
    # Generate filename with date
    filename = f"leads_{utc_now().strftime('%Y-%m-%d')}.csv"
    
    current_app.logger.info(f"[Leads] CSV export for agent {agent['id']} ({len(leads)} leads)")
    
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={
            'Content-Disposition': f'attachment; filename="{filename}"'
        }
    )
