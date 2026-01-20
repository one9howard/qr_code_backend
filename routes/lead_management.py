"""
Lead Management Routes - Dashboard for managing buyer leads.

Provides:
- GET /dashboard/leads - List all leads (filtered)
- GET /dashboard/leads/<id> - Lead detail view
- POST /api/leads/<id>/status - Update status
- POST /api/leads/<id>/notes - Add note
- POST /api/leads/<id>/tasks - Add/Complete task

Security:
- Login Required
- Ownership Verification (Lead -> Property -> Agent -> User)
"""
from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, abort
from flask_login import login_required, current_user
from database import get_db
from utils.timestamps import utc_now, utc_iso

lead_management_bp = Blueprint('lead_management', __name__)

def verify_lead_access(lead_id):
    """
    Verify current user owns the agent that owns the property that owns the lead.
    Returns lead row if authorized, else raises 403 or 404.
    """
    db = get_db()
    lead = db.execute("""
        SELECT l.*, p.address as property_address, a.name as agent_name
        FROM leads l
        JOIN agents a ON l.agent_id = a.id
        JOIN properties p ON l.property_id = p.id
        WHERE l.id = %s AND a.user_id = %s
    """, (lead_id, current_user.id)).fetchone()
    
    if not lead:
        abort(404) # Or 403, but 404 leaks less info
        
    return lead

@lead_management_bp.route("/dashboard/leads")
@login_required
def list_leads():
    """List all leads with optional filtering."""
    db = get_db()
    
    # Filters
    status_filter = request.args.get('status')
    property_filter = request.args.get('property_id')
    
    query = """
        SELECT l.*, p.address as property_address
        FROM leads l
        JOIN agents a ON l.agent_id = a.id
        JOIN properties p ON l.property_id = p.id
        WHERE a.user_id = %s
    """
    params = [current_user.id]
    
    if status_filter:
        query += " AND l.status = %s"
        params.append(status_filter)
        
    if property_filter:
        query += " AND l.property_id = %s"
        params.append(property_filter)
        
    query += " ORDER BY l.created_at DESC"
    
    leads = db.execute(query, tuple(params)).fetchall()
    
    # Get properties for filter dropdown
    properties = db.execute("""
        SELECT p.id, p.address 
        FROM properties p
        JOIN agents a ON p.agent_id = a.id
        WHERE a.user_id = %s
        ORDER BY p.created_at DESC
    """, (current_user.id,)).fetchall()
    
    return render_template(
        "dashboard/leads_list.html",
        leads=leads,
        properties=properties,
        current_filter={'status': status_filter, 'property_id': property_filter}
    )

@lead_management_bp.route("/dashboard/leads/<int:lead_id>")
@login_required
def lead_detail(lead_id):
    """Lead detail view with timeline, notes, tasks."""
    lead = verify_lead_access(lead_id)
    db = get_db()
    
    # Fetch related data
    notes = db.execute("SELECT * FROM lead_notes WHERE lead_id = %s ORDER BY created_at DESC", (lead_id,)).fetchall()
    tasks = db.execute("SELECT * FROM lead_tasks WHERE lead_id = %s ORDER BY created_at ASC", (lead_id,)).fetchall()
    events = db.execute("SELECT * FROM lead_events WHERE lead_id = %s ORDER BY created_at DESC", (lead_id,)).fetchall()
    
    return render_template(
        "dashboard/lead_detail.html",
        lead=lead,
        notes=notes,
        tasks=tasks,
        events=events
    )

# --- API Actions ---

@lead_management_bp.route("/api/leads/<int:lead_id>/status", methods=["POST"])
@login_required
def update_status(lead_id):
    """Update lead status."""
    verify_lead_access(lead_id)
    
    new_status = request.form.get("status")
    if not new_status:
        return jsonify({"success": False, "error": "Status required"}), 400
        
    db = get_db()
    
    # Audit log
    db.execute("""
        INSERT INTO lead_events (lead_id, event_type, payload, actor_user_id, created_at)
        VALUES (%s, 'status_change', %s, %s, %s)
    """, (lead_id, f"Status changed to {new_status}", current_user.id, utc_iso()))
    
    # Update lead
    db.execute("UPDATE leads SET status = %s WHERE id = %s", (new_status, lead_id))
    db.commit()
    
    return jsonify({"success": True})

@lead_management_bp.route("/api/leads/<int:lead_id>/notes", methods=["POST"])
@login_required
def add_note(lead_id):
    """Add a note to a lead."""
    verify_lead_access(lead_id)
    
    body = request.form.get("body", "").strip()
    if not body:
        return jsonify({"success": False, "error": "Body required"}), 400
        
    db = get_db()
    
    # Insert note
    db.execute("""
        INSERT INTO lead_notes (lead_id, actor_user_id, body, created_at)
        VALUES (%s, %s, %s, %s)
    """, (lead_id, current_user.id, body, utc_iso()))
    
    # Audit log
    db.execute("""
        INSERT INTO lead_events (lead_id, event_type, payload, actor_user_id, created_at)
        VALUES (%s, 'note_added', %s, %s, %s)
    """, (lead_id, "Added a note", current_user.id, utc_iso()))
    
    db.commit()
    
    # Return redirects for form submissions to refresh page
    return redirect(url_for('lead_management.lead_detail', lead_id=lead_id))

@lead_management_bp.route("/api/leads/<int:lead_id>/tasks", methods=["POST"])
@login_required
def manage_tasks(lead_id):
    """Create or update a task."""
    verify_lead_access(lead_id)
    db = get_db()
    
    action = request.form.get("action")
    
    if action == "create":
        title = request.form.get("title")
        if not title:
            flash("Task title required", "error")
        else:
            db.execute("""
                INSERT INTO lead_tasks (lead_id, assigned_to_user_id, title, status, created_at)
                VALUES (%s, %s, %s, 'open', %s)
            """, (lead_id, current_user.id, title, utc_iso()))
            
            db.execute("""
                INSERT INTO lead_events (lead_id, event_type, payload, actor_user_id, created_at)
                VALUES (%s, 'task_created', %s, %s, %s)
            """, (lead_id, f"Created task: {title}", current_user.id, utc_iso()))

    elif action == "complete":
        task_id = request.form.get("task_id")
        db.execute("""
            UPDATE lead_tasks SET status = 'done', completed_at = %s
            WHERE id = %s AND lead_id = %s
        """, (utc_iso(), task_id, lead_id))
        
        db.execute("""
            INSERT INTO lead_events (lead_id, event_type, payload, actor_user_id, created_at)
            VALUES (%s, 'task_completed', %s, %s, %s)
        """, (lead_id, f"Completed task {task_id}", current_user.id, utc_iso()))

    db.commit()
    return redirect(url_for('lead_management.lead_detail', lead_id=lead_id))
