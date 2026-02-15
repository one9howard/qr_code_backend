import logging
import json
from datetime import datetime, timezone
from database import get_db

logger = logging.getLogger(__name__)

JOB_STATUS_QUEUED = 'queued'
JOB_STATUS_PROCESSING = 'processing'
JOB_STATUS_DONE = 'done'
JOB_STATUS_DEAD = 'dead'
MAX_RETRY_ATTEMPTS = 5

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
        SET status = '{JOB_STATUS_PROCESSING}',
            locked_at = NOW(),
            attempts = attempts + 1,
            updated_at = NOW(),
            next_run_at = NULL
        WHERE id IN (
            SELECT id
            FROM async_jobs
            WHERE (
                (status = '{JOB_STATUS_QUEUED}' AND (next_run_at IS NULL OR next_run_at <= NOW()))
                OR (status = '{JOB_STATUS_PROCESSING}' AND locked_at < NOW() - INTERVAL '5 minutes')
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
        f"UPDATE async_jobs SET status='{JOB_STATUS_DONE}', updated_at=NOW() WHERE id=%s",
        (job_id,)
    )
    db.commit()
    logger.info(f"[Async] Job {job_id} marked DONE")

def mark_failed(job_id, error, can_retry=True):
    """
    Mark job failed, scheduling retry if applicable.
    """
    db = get_db()

    # Exponential backoff: 60s, 120s, 240s, 480s...
    # attempts is incremented in claim_batch before processing starts.
    retry_case = f"""
        CASE
            WHEN %s AND attempts < {MAX_RETRY_ATTEMPTS} THEN '{JOB_STATUS_QUEUED}'
            ELSE '{JOB_STATUS_DEAD}'
        END
    """
    sql = f"""
        UPDATE async_jobs
        SET status = {retry_case},
            last_error = %s,
            updated_at = NOW(),
            next_run_at = CASE
                WHEN %s AND attempts < {MAX_RETRY_ATTEMPTS}
                    THEN NOW() + (power(2, GREATEST(attempts - 1, 0)) * interval '60 seconds')
                ELSE NULL
            END
        WHERE id = %s
        RETURNING status, next_run_at, attempts
    """

    row = db.execute(sql, (can_retry, str(error), can_retry, job_id)).fetchone()
    db.commit()

    if row:
        new_status = row['status']
        next_run = row['next_run_at']
        attempts = row['attempts']
        if new_status == JOB_STATUS_QUEUED:
            logger.warning(
                f"[Async] Job {job_id} failed (attempt={attempts}, retry_at={next_run}): {error}"
            )
        else:
            logger.error(f"[Async] Job {job_id} marked DEAD (attempt={attempts}): {error}")
