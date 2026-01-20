#!/usr/bin/env python3
import sys
import os
import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from database import get_db
from utils.storage import get_storage
from utils.timestamps import utc_iso

def export_jobs(limit=50, dry_run=False, overwrite=False, app=None):
    """
    Export pending print jobs to local inbox.
    
    Args:
        limit (int): Max jobs to process
        dry_run (bool): If True, verify without writing/mutating
        app (Flask): Optional Flask app instance (for testing)
    """
    if app is None:
        app = create_app()
        
    with app.app_context():
        db = get_db()
        storage = get_storage()
        
        inbox_dir = os.environ.get("PRINT_INBOX_DIR", "/opt/insite_print_worker/inbox")
        if not dry_run:
            os.makedirs(inbox_dir, exist_ok=True)
            
        print(f"[Exporter] Inbox Directory: {inbox_dir}")
        print(f"[Exporter] Storage Backend: {storage.__class__.__name__}")
        
        # Select queued jobs
        # Optional: retry logic if 'last_error' is present? 
        # For now, simplistic approach: status='queued' or 'failed' (if we want to retry failed ones manually)
        # The checklist says "queued" and "failed".
        
        query = """
            SELECT j.*, o.id as order_id, o.property_id, o.created_at as order_created_at
            FROM print_jobs j
            JOIN orders o ON j.order_id = o.id
            WHERE j.status IN ('queued', 'failed')
            ORDER BY j.created_at ASC
            LIMIT %s
        """
        
        # Cursor factory might vary, so we convert rows to dicts
        cursor = db.execute(query, (limit,))
        columns = [col[0] for col in cursor.description]
        jobs = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        if not jobs:
            print("[Exporter] No queued jobs found.")
            return

        print(f"[Exporter] Found {len(jobs)} jobs to process.")
        
        for job in jobs:
            # Correctly identify UUID
            job_uuid = job['job_id']
            order_id = job['order_id']
            filename = job['filename'] # Storage key
            
            print(f"--- Processing Job {job_uuid} (Order {order_id}) ---")
            
            # Strict Naming: <job_id>.pdf / .json
            dest_pdf_name = f"{job_uuid}.pdf"
            dest_json_name = f"{job_uuid}.json"
            
            dest_pdf_path = os.path.join(inbox_dir, dest_pdf_name)
            dest_json_path = os.path.join(inbox_dir, dest_json_name)
            
            if not overwrite and (os.path.exists(dest_pdf_path) or os.path.exists(dest_json_path)):
                print(f"  [SKIP] Files already exist for job {job_uuid} (use --overwrite to force)")
                continue

            if dry_run:
                print(f"  [DRY-RUN] Will download {filename} -> {dest_pdf_path}")
                print(f"  [DRY-RUN] Will write manifest -> {dest_json_path}")
                print(f"  [DRY-RUN] Will update DB status to 'downloaded'")
                continue
                
            # 1. Download PDF
            try:
                print(f"  Downloading {filename}...")
                pdf_bytes = storage.get_file(filename)
                
                if not pdf_bytes:
                    print(f"  [ERROR] Storage returned empty bytes for {filename}")
                    continue
                    
                with open(dest_pdf_path, 'wb') as f:
                    f.write(pdf_bytes.read() if hasattr(pdf_bytes, 'read') else pdf_bytes)
                    
            except Exception as e:
                print(f"  [ERROR] Failed to download PDF: {e}")
                import traceback
                traceback.print_exc()
                continue
                
            # 2. Write Manifest
            try:
                manifest = {
                    "job_id": job_uuid,
                    "order_id": order_id,
                    "property_id": job['property_id'],
                    "shipping_json": job['shipping_json'],
                    "created_at": str(job['created_at']),
                    # Optional: "exported_at": utc_iso()
                }
                with open(dest_json_path, 'w') as f:
                    json.dump(manifest, f, indent=2)
                    
            except Exception as e:
                print(f"  [ERROR] Failed to write manifest: {e}")
                # Cleanup PDF?
                continue
                
            # 3. Update DB
            try:
                db.execute(
                    """
                    UPDATE print_jobs 
                    SET status = 'downloaded', 
                        attempts = COALESCE(attempts, 0) + 1
                    WHERE job_id = %s
                    """,
                    (job_uuid,)
                )
                db.commit()
                print(f"  [SUCCESS] Exported and updated status.")
            except Exception as e:
                print(f"  [ERROR] DB update failed: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export print jobs to local inbox")
    parser.add_argument("--limit", type=int, default=10, help="Max jobs to process")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without writing")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing files")
    
    args = parser.parse_args()
    
    export_jobs(limit=args.limit, dry_run=args.dry_run, overwrite=args.overwrite)
