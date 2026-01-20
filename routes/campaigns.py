"""
Campaign Management Routes - Create and manage marketing campaigns and QR variants.

Provides:
- GET /dashboard/properties/<id>/campaigns - List campaigns for a property
- POST /api/properties/<id>/campaigns - Create new campaign
- POST /api/campaigns/<id>/variants - Create new QR variant
"""
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from database import get_db
from utils.timestamps import utc_now, utc_iso
import secrets

campaigns_bp = Blueprint('campaigns', __name__)

def generate_variant_code():
    """Generate unique code for QR variant."""
    db = get_db()
    while True:
        code = secrets.token_urlsafe(6) # 8 chars
        if not db.execute("SELECT 1 FROM qr_variants WHERE code = %s", (code,)).fetchone():
            return code

@campaigns_bp.route("/dashboard/properties/<int:property_id>/campaigns")
@login_required
def list_campaigns(property_id):
    """List campaigns and variants for a property."""
    db = get_db()
    
    # Verify ownership
    property_row = db.execute("""
        SELECT p.*, a.name as agent_name 
        FROM properties p
        JOIN agents a ON p.agent_id = a.id
        WHERE p.id = %s AND a.user_id = %s
    """, (property_id, current_user.id)).fetchone()
    
    if not property_row:
        flash("Property not found or access denied", "error")
        return redirect(url_for('dashboard.index'))
        
    # Fetch campaigns
    campaigns = db.execute("""
        SELECT * FROM campaigns WHERE property_id = %s ORDER BY created_at DESC
    """, (property_id,)).fetchall()
    
    # Fetch all variants for this property
    variants = db.execute("""
        SELECT v.*, c.name as campaign_name
        FROM qr_variants v
        LEFT JOIN campaigns c ON v.campaign_id = c.id
        WHERE v.property_id = %s
        ORDER BY v.created_at DESC
    """, (property_id,)).fetchall()
    
    return render_template(
        "dashboard/campaigns.html",
        property=property_row,
        campaigns=campaigns,
        variants=variants
    )

@campaigns_bp.route("/api/properties/<int:property_id>/campaigns", methods=["POST"])
@login_required
def create_campaign(property_id):
    """Create a new campaign."""
    db = get_db()
    
    # Verify ownership
    if not db.execute("""
        SELECT 1 FROM properties p
        JOIN agents a ON p.agent_id = a.id
        WHERE p.id = %s AND a.user_id = %s
    """, (property_id, current_user.id)).fetchone():
        return jsonify({"success": False, "error": "Access denied"}), 403
        
    name = request.form.get("name")
    if not name:
        return jsonify({"success": False, "error": "Name required"}), 400
        
    db.execute("""
        INSERT INTO campaigns (property_id, name, created_at)
        VALUES (%s, %s, %s)
    """, (property_id, name, utc_iso()))
    db.commit()
    
    return redirect(url_for('campaigns.list_campaigns', property_id=property_id))

@campaigns_bp.route("/api/properties/<int:property_id>/variants", methods=["POST"])
@login_required
def create_variant(property_id):
    """Create a new QR variant."""
    db = get_db()
    
    # Verify ownership
    if not db.execute("""
        SELECT 1 FROM properties p
        JOIN agents a ON p.agent_id = a.id
        WHERE p.id = %s AND a.user_id = %s
    """, (property_id, current_user.id)).fetchone():
        return jsonify({"success": False, "error": "Access denied"}), 403
        
    campaign_id = request.form.get("campaign_id")
    label = request.form.get("label")
    
    if not label:
        return jsonify({"success": False, "error": "Label required"}), 400
        
    code = generate_variant_code()
    
    db.execute("""
        INSERT INTO qr_variants (property_id, campaign_id, code, label, created_at)
        VALUES (%s, %s, %s, %s, %s)
    """, (property_id, campaign_id if campaign_id else None, code, label, utc_iso()))
    db.commit()
    
    return redirect(url_for('campaigns.list_campaigns', property_id=property_id))
