import pytest

# --- Fixtures ---

@pytest.fixture
def atomic_data(db):
    """Setup print job data."""
    # User / Agent / Property / Order
    user_id = db.execute(
        "INSERT INTO users (email, password_hash, is_verified) VALUES (%s, %s, %s) RETURNING id",
        ('atomic@test.com', 'hash', True)
    ).fetchone()['id']

    agent_id = db.execute(
        "INSERT INTO agents (user_id, name, brokerage, email, phone) VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (user_id, 'Atomic Agent', 'Brokerage', 'atomic@test.com', '555-1234')
    ).fetchone()['id']

    prop_id = db.execute(
        "INSERT INTO properties (agent_id, address, beds, baths, slug, qr_code) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
        (agent_id, '123 Atomic St', '3', '2', 'atomic-slug', 'atomic-qr')
    ).fetchone()['id']

    order_id = db.execute(
        "INSERT INTO orders (property_id, user_id, status, order_type) VALUES (%s, %s, %s, %s) RETURNING id",
        (prop_id, user_id, 'submitted_to_printer', 'sign')
    ).fetchone()['id']

    # Print Job 1: queued
    job_id = "job-123"
    db.execute(
        """INSERT INTO print_jobs (idempotency_key, job_id, order_id, filename, status, shipping_json, attempts, next_retry_at)
           VALUES (%s, %s, %s, %s, 'queued', %s, 0, NULL)""",
        ('idem-1', job_id, order_id, 's3-key-1', '{}')
    )

    db.commit()
    return {'order_id': order_id, 'job_id': job_id}


# --- Tests ---

def test_claim_jobs_success(client, db, atomic_data):
    """Test correctly claiming a queued job."""
    from config import PRINT_JOBS_TOKEN
    headers = {'Authorization': f"Bearer {PRINT_JOBS_TOKEN}"}

    resp = client.post('/api/print-jobs/claim?limit=1', headers=headers)
    assert resp.status_code == 200
    data = resp.json

    assert len(data['jobs']) == 1
    job = data['jobs'][0]
    assert job['job_id'] == atomic_data['job_id']
    assert job['status'] == 'claimed'

    # Verify DB update
    row = db.execute("SELECT status FROM print_jobs WHERE job_id=%s", (atomic_data['job_id'],)).fetchone()
    assert row['status'] == 'claimed'


def test_claim_unauthorized(client):
    """Test claim without token fails."""
    resp = client.post('/api/print-jobs/claim')
    assert resp.status_code == 401


def test_mark_downloaded_transition(client, db, atomic_data):
    """Test transition from claimed to downloaded."""
    from config import PRINT_JOBS_TOKEN
    headers = {'Authorization': f"Bearer {PRINT_JOBS_TOKEN}"}
    job_id = atomic_data['job_id']

    # Ensure claimed status
    db.execute("UPDATE print_jobs SET status='claimed' WHERE job_id=%s", (job_id,))
    db.commit()

    # 1. Successful ACK
    resp = client.post(f'/api/print-jobs/{job_id}/downloaded', headers=headers)
    assert resp.status_code == 200
    assert resp.json['success'] is True

    # Check DB
    row = db.execute("SELECT status FROM print_jobs WHERE job_id=%s", (job_id,)).fetchone()
    assert row['status'] == 'downloaded'

    # 2. Idempotency (already downloaded/printed)
    db.execute("UPDATE print_jobs SET status='printed' WHERE job_id=%s", (job_id,))
    db.commit()

    resp = client.post(f'/api/print-jobs/{job_id}/downloaded', headers=headers)
    assert resp.status_code == 200
    assert resp.json.get('note') == 'already_processed' or resp.json['success'] is True

