import os
import json
import uuid
from . import FulfillmentProvider
from database import get_db

class InternalQueueProvider(FulfillmentProvider):
    """
    Default provider that inserts jobs into the local `print_jobs` table
    for processing by the internal print server (or manual export).
    """
    
    def submit_order(self, order_id: int, shipping_data: dict, pdf_path: str) -> str:
        db = get_db()
        from utils.storage import get_storage
        storage = get_storage()
        
        # Generate a job ID (used as provider_job_id)
        job_id = str(uuid.uuid4())
        
        # Idempotency Key (using order_id as base is safe for internal)
        idempotency_key = f"order_{order_id}"
        
        # Check idempotency first (to avoid re-uploading)
        existing_job = db.execute(
            "SELECT job_id FROM print_jobs WHERE idempotency_key = %s", 
            (idempotency_key,)
        ).fetchone()
        
        if existing_job:
            import logging
            logging.getLogger(__name__).info(f"[InternalProvider] Idempotent: Job {existing_job['job_id']} already exists")
            return existing_job['job_id']

        # Parse shipping data to JSON
        shipping_json = json.dumps(shipping_data) if shipping_data else None
        
        # Prepare storage paths
        # Internal print server expects files in `print-jobs/` container/folder
        # We rename to {job_id}.pdf to ensure uniqueness and clean names for printer
        storage_filename = f"{job_id}.pdf"
        storage_key = f"print-jobs/{storage_filename}"
        
        # Copy file in storage using the new efficient copy method
        if not storage.exists(pdf_path):
             raise FileNotFoundError(f"Source PDF {pdf_path} not found in storage")
             
        # Use copy() to duplicate the file to print-jobs location
        # This handles S3-to-S3 copy efficiently or Local-to-Local copy
        storage.copy(pdf_path, storage_key)
        
        # Insert into print_jobs queue
        db.execute('''
            INSERT INTO print_jobs (
                idempotency_key, job_id, order_id, filename, status, shipping_json, attempts
            ) VALUES (%s, %s, %s, %s, 'queued', %s, 0)
        ''', (idempotency_key, job_id, order_id, storage_key, shipping_json))
        db.commit()
            
        return job_id

    def cancel_order(self, provider_job_id: str) -> bool:
        db = get_db()
        db.execute("UPDATE print_jobs SET status = 'cancelled' WHERE job_id = %s", (provider_job_id,))
        db.commit()
        return True

    def get_status(self, provider_job_id: str) -> dict:
        db = get_db()
        row = db.execute("SELECT status FROM print_jobs WHERE job_id = %s", (provider_job_id,)).fetchone()
        if row:
            return {'status': row['status']}
        return {'status': 'unknown'}
