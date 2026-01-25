import logging
import json
from datetime import datetime, timezone
from database import get_db

logger = logging.getLogger(__name__)

JOB_STATUS_QUEUED = 'queued'
JOB_STATUS_PROCESSING = 'processing'
JOB_STATUS_DONE = 'done'
JOB_STATUS_FAILED = 'failed'

def enqueue(job_type, payload):
    """
    Enqueue a new job.
    payload should be a dict (serialized to JSONB).
    Returns job_id.
    """
    db = get_db()
    if not isinstance(payload, str):
        payload_json = json.dumps(payload)
    else:
        payload_json = payload

    cursor = db.execute(
        """
        INSERT INTO async_jobs (job_type, payload, status)
        VALUES (%s, %s, 'queued')
        RETURNING id
        """,
        (job_type, payload_json)
    )
    db.commit()
    job_id = cursor.fetchone()['id']
    logger.info(f"[Async] Enqueued {job_type} job {job_id}")
    return job_id

def claim_batch(job_types=None, limit=10):
    """
    Atomically claim a batch of queued jobs.
    Returns list of job dicts.
    """
    db = get_db()
    
    # Filter by specific types if provided
    type_clause = ""
    params = [limit]
    
    if job_types:
        placeholders = ','.join(['%s'] * len(job_types))
        type_clause = f"AND job_type IN ({placeholders})"
        params = job_types + params # Prepend parameters for IN clause

    # SKIP LOCKED is key for concurrency safety
    query = f"""
        UPDATE async_jobs
        SET status = 'processing',
            locked_at = NOW(),
            attempts = attempts + 1,
            updated_at = NOW()
        WHERE id IN (
            SELECT id
            FROM async_jobs
            WHERE status = 'queued'
            {type_clause}
            ORDER BY created_at ASC
            LIMIT %s
            FOR UPDATE SKIP LOCKED
        )
        RETURNING id, job_type, payload, attempts
    """
    
    # Note: params order needs to be careful.
    # The subquery takes params for type_clause then LIMIT.
    # The outer query uses no new params.
    # So `params` constructed above [t1, t2, ..., limit] is correct.
    
    cursor = db.execute(query, tuple(params))
    db.commit()
    jobs = cursor.fetchall()
    
    if jobs:
        logger.info(f"[Async] Claimed {len(jobs)} jobs")
        
    # Convert Row objects to dicts if needed, or return as is (dict-like)
    return [dict(j) for j in jobs]

def mark_done(job_id):
    db = get_db()
    db.execute(
        "UPDATE async_jobs SET status='done', updated_at=NOW() WHERE id=%s",
        (job_id,)
    )
    db.commit()
    logger.info(f"[Async] Job {job_id} marked DONE")

def mark_failed(job_id, error, can_retry=False):
    db = get_db()
    # Logic: if attempts < MAX and can_retry -> queued? 
    # For now, simplistic hard fail or manual retry logic.
    # We leave status as 'failed', operator can reset to 'queued'.
    
    status = 'failed' 
    # Optional retry logic could go here
    
    db.execute(
        "UPDATE async_jobs SET status=%s, last_error=%s, updated_at=NOW() WHERE id=%s",
        (status, str(error), job_id)
    )
    db.commit()
    logger.error(f"[Async] Job {job_id} marked FAILED: {error}")
