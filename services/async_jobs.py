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

    query = f"""
        UPDATE async_jobs
        SET status = 'processing',
            locked_at = NOW(),
            attempts = attempts + 1,
            updated_at = NOW(),
            next_run_at = NULL
        WHERE id IN (
            SELECT id
            FROM async_jobs
            WHERE (
                (status = 'queued' AND (next_run_at IS NULL OR next_run_at <= NOW()))
                OR (status = 'processing' AND locked_at < NOW() - INTERVAL '5 minutes')
                OR (status = 'failed' AND attempts < 5 AND next_run_at <= NOW())
            )
            {type_clause}
            ORDER BY next_run_at NULLS FIRST, created_at ASC
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

def mark_failed(job_id, error, can_retry=True):
    """
    Mark job failed, scheduling retry if applicable.
    """
    db = get_db()
    
    # Exponential backoff: 30s, 2m, 10m, etc.
    # attempts is incremented on claim.
    # If currently attempts < 5, queue it for retry.
    
    # We rely on the current DB state invalidating attempts if concurrent? 
    # No, we just blindly set status based on attempts count from DB context or blindly update.
    # Let's do logic in SQL.
    
    sql = """
        UPDATE async_jobs 
        SET status = CASE 
                WHEN attempts < 5 THEN 'failed' -- Will be picked up by claim_batch 'failed' clause
                ELSE 'failed' -- Terminal state if max attempts ('dead' if we want distinction, user said 'dead')
            END,
            status = CASE WHEN attempts < 5 THEN 'failed' ELSE 'dead' END,
            last_error = %s,
            updated_at = NOW(),
            next_run_at = CASE 
                WHEN attempts < 5 THEN NOW() + (power(2, attempts) * interval '30 seconds')
                ELSE NULL 
            END
        WHERE id = %s
        RETURNING status, next_run_at
    """
    # Wait, user said: "set status='queued' if attempts < MAX"
    # But my claim logic picks up 'failed' too: OR (status = 'failed' AND attempts < 5 ...)
    # If I set it to 'queued', it's standard.
    # Let's stick to user request: "set status='queued' if attempts < MAX"
    # Terminal status='dead'.
    
    sql = """
        UPDATE async_jobs 
        SET status = CASE 
                WHEN attempts < 5 THEN 'queued' 
                ELSE 'dead'
            END,
            last_error = %s,
            updated_at = NOW(),
            next_run_at = CASE 
                WHEN attempts < 5 THEN NOW() + (power(2, attempts) * interval '30 seconds')
                ELSE NULL 
            END
        WHERE id = %s
        RETURNING status, next_run_at
    """
    
    row = db.execute(sql, (str(error), job_id)).fetchone()
    db.commit()
    
    if row:
        new_status = row['status']
        next_run = row['next_run_at']
        if new_status == 'queued':
            logger.warning(f"[Async] Job {job_id} failed (will retry at {next_run}): {error}")
        else:
            logger.error(f"[Async] Job {job_id} DIED (Max attempts): {error}")
