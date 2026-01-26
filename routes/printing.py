import os
from flask import Blueprint, request, jsonify, current_app, url_for, send_file
from database import get_db
from utils.storage import get_storage
import secrets
from constants import ORDER_STATUS_FULFILLED

printing_bp = Blueprint('printing', __name__, url_prefix='/api/print-jobs')

def check_auth():
    """Verify Bearer token matches PRINT_JOBS_TOKEN constant-time."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return False
    token = auth_header.split(" ", 1)[1].strip()
    
    # Import at call time to pick up test-time value
    from config import PRINT_JOBS_TOKEN
    expected = (PRINT_JOBS_TOKEN or "").strip()
    
    if not expected:
        return False
    return secrets.compare_digest(token, expected)

@printing_bp.route("/<job_id>/pdf", methods=["GET"])
def download_job_pdf(job_id):
    """
    Authenticated endpoint to stream the print PDF from storage.
    """
    if not check_auth():
        return jsonify({"error": "Unauthorized"}), 401
    
    db = get_db()
    job = db.execute("SELECT filename FROM print_jobs WHERE job_id = %s", (job_id,)).fetchone()
    if not job:
        return jsonify({"error": "Job not found"}), 404
        
    storage = get_storage()
    if not storage.exists(job['filename']):
        return jsonify({"error": "PDF file missing"}), 404
        
    try:
        # Stream file from storage
        file_bytes = storage.get_file(job['filename'])
        return send_file(
            file_bytes,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"print_job_{job_id}.pdf"
        )
    except Exception as e:
        current_app.logger.error(f"[Printing] Error serving PDF for job {job_id}: {e}")
        return jsonify({"error": "Internal Error"}), 500


@printing_bp.route("/claim", methods=["POST"])
def claim_jobs():
    """
    Atomically claim pending print jobs for a worker.
    Uses FOR UPDATE SKIP LOCKED to prevent duplicate claims.
    
    Query Params:
      limit (int): Max jobs to claim (default 10, max 50)
      
    Returns:
      JSON list of claimed jobs with download URLs.
    """
    if not check_auth():
        return jsonify({"error": "Unauthorized"}), 401
    
    limit = request.args.get('limit', 10, type=int)
    limit = min(limit, 50) # Cap limit
    
    db = get_db()
    claimed_jobs = []
    
    try:
        # Atomic Claim Query
        # 1. Select candidates (queued OR claimed+expired)
        # 2. Lock rows with SKIP LOCKED
        # 3. Update status and retry time
        # 4. Return details
        # Atomic Claim Query
        # 1. Select candidates (queued OR claimed+expired)
        # 2. Lock rows with SKIP LOCKED
        # 3. Update status and retry time
        query = """
            WITH claimed AS (
                SELECT job_id 
                FROM print_jobs 
                WHERE (
                    (status = 'queued' AND (next_retry_at IS NULL OR next_retry_at <= CURRENT_TIMESTAMP))
                    OR (status = 'claimed' AND claimed_at < CURRENT_TIMESTAMP - INTERVAL '10 minutes')
                )
                ORDER BY created_at ASC 
                LIMIT %s
                FOR UPDATE SKIP LOCKED
            )
            UPDATE print_jobs
            SET status = 'claimed', 
                next_retry_at = CURRENT_TIMESTAMP + interval '5 minutes',
                attempts = COALESCE(attempts, 0) + 1,
                claimed_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            FROM claimed
            WHERE print_jobs.job_id = claimed.job_id
            RETURNING print_jobs.*;
        """
        claimed_jobs = db.execute(query, (limit,)).fetchall()
        db.commit()
        
    except Exception as e:
        current_app.logger.error(f"[Printing] Claim failed: {e}")
        db.rollback()
        return jsonify({"error": "Queue error", "details": str(e)}), 500
            
    results = []
    
    for job in claimed_jobs:
        # Construct URLs
        j_id = job['job_id']
        download_url = url_for('printing.download_job_pdf', job_id=j_id, _external=True)
        
        results.append({
            "job_id": j_id,
            "order_id": job['order_id'],
            "filename": job['filename'],
            "status": job['status'],
            "download_url": download_url,
            "shipping_json": job['shipping_json'],
            "created_at": job['created_at'].isoformat() if job['created_at'] else None
        })
        
    # Phase 5: Inject Print Metadata
    if results:
        order_ids = [r['order_id'] for r in results]
        meta_rows = db.execute(
            "SELECT id, print_product, material, sides, layout_id FROM orders WHERE id = ANY(%s)",
            (order_ids,)
        ).fetchall()
        meta_map = {r['id']: r for r in meta_rows}
        
        for r in results:
            om = meta_map.get(r['order_id'])
            if om:
                r.update({
                    "print_product": om['print_product'],
                    "material": om['material'],
                    "sides": om['sides'],
                    "layout_id": om['layout_id']
                })
        
    return jsonify({"jobs": results})

@printing_bp.route("/<job_id>/downloaded", methods=["POST"])
def mark_downloaded(job_id):
    """
    Mark a job as successfully downloaded by the worker.
    Transition: claimed -> downloaded
    """
    if not check_auth():
        return jsonify({"error": "Unauthorized"}), 401
        
    db = get_db()
    
    # Check current status
    row = db.execute("SELECT status FROM print_jobs WHERE job_id = %s", (job_id,)).fetchone()
    if not row:
        return jsonify({"error": "Job not found"}), 404
        
    current = row['status']
    
    # Idempotency
    if current in ('downloaded', 'printed'):
        return jsonify({"success": True, "note": "already_processed"})
        
    if current not in ('queued', 'claimed'):
        return jsonify({"error": f"Invalid transition from {current}"}), 400
        
    try:
        db.execute(
            "UPDATE print_jobs SET status = 'downloaded', next_retry_at = NULL, downloaded_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE job_id = %s",
            (job_id,)
        )
        db.commit()
        return jsonify({"success": True})
    except Exception as e:
        current_app.logger.error(f"[Printing] Mark downloaded failed: {e}")
        return jsonify({"error": "Update failed"}), 500

@printing_bp.route("/<job_id>/printed", methods=["POST"])
def mark_printed(job_id):
    """Mark job as printed (complete)."""
    if not check_auth():
        return jsonify({"error": "Unauthorized"}), 401
        
    db = get_db()
    
    # 1. Verify current status (Transition Guard)
    row = db.execute("SELECT status FROM print_jobs WHERE job_id = %s", (job_id,)).fetchone()
    if not row:
        return jsonify({"error": "Job not found"}), 404
        
    current_status = row['status']
    
    if current_status == 'printed':
        return jsonify({"success": True, "note": "already_printed"})
    
    # Strict flow: should come from downloaded, but we allow claimed/queued for manual overrides
    if current_status not in ('queued', 'claimed', 'downloaded'):
        return jsonify({"error": f"Invalid transition from {current_status}"}), 400

    # 2. Update Print Job
    db.execute(
        "UPDATE print_jobs SET status = 'printed', next_retry_at = NULL, printed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE job_id = %s",
        (job_id,)
    )
    
    # 3. Update Order Reference
    db.execute('''
        UPDATE orders 
        SET status = %s, fulfilled_at = CURRENT_TIMESTAMP 
        WHERE provider_job_id = %s
    ''', (ORDER_STATUS_FULFILLED, job_id))
    
    db.commit()
    return jsonify({"success": True})
