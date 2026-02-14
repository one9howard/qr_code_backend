"""
Test Fulfillment Pipeline

Verifies:
1. fulfill_order enqueues a print_jobs row
2. orders.status becomes 'submitted_to_printer'
3. Second fulfill_order call is idempotent (no duplicate print_jobs)
"""
import pytest


def test_fulfill_order_enqueues_one_print_job(db, app):
    """Test that fulfill_order creates print_job and updates order status."""
    # Setup: user -> agent -> property -> order
    user_id = db.execute(
        "INSERT INTO users (email, password_hash, is_verified, is_admin) VALUES (%s, %s, %s, %s) RETURNING id",
        ("u@example.com", "x", True, False),
    ).fetchone()[0]
    
    agent_id = db.execute(
        "INSERT INTO agents (user_id, name, brokerage, email, phone, photo_filename) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
        (user_id, "Agent", "Broker", "a@example.com", None, None),
    ).fetchone()[0]
    
    property_id = db.execute(
        "INSERT INTO properties (agent_id, address, beds, baths, sqft, price, description, slug, qr_code) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (agent_id, "123 Test St", "3", "2", "1000", "$1,250,000", "desc", "slug", "qr1"),
    ).fetchone()[0]

    # Setup: source PDF in storage
    from utils.storage import get_storage
    storage = get_storage()
    source_key = f"uploads/orders/order_test.pdf"
    storage.put_file(b"%PDF-1.4\n%%EOF\n", source_key)

    # Create order with 'paid' status
    order_id = db.execute(
        """INSERT INTO orders (user_id, property_id, sign_pdf_path, status, order_type, paid_at)
           VALUES (%s, %s, %s, 'paid', 'sign', NOW()) RETURNING id""",
        (user_id, property_id, source_key),
    ).fetchone()[0]
    db.commit()

    from services.fulfillment import fulfill_order

    # First call should succeed
    ok1 = fulfill_order(order_id)
    assert ok1 is True

    # Second call should also succeed (idempotent)
    ok2 = fulfill_order(order_id)
    assert ok2 is True

    # Verify: order status is 'submitted_to_printer'
    status = db.execute(
        "SELECT status FROM orders WHERE id = %s", (order_id,)
    ).fetchone()[0]
    assert status == 'submitted_to_printer'

    # Verify: exactly one print_job exists
    jobs = db.execute(
        "SELECT * FROM print_jobs WHERE order_id = %s", (order_id,)
    ).fetchall()
    assert len(jobs) == 1
    assert jobs[0]['status'] == 'queued'


def test_fulfill_order_idempotency(db, app):
    """Test that duplicate calls don't create duplicate print_jobs."""
    # Setup minimal order
    user_id = db.execute(
        "INSERT INTO users (email, password_hash, is_verified, is_admin) VALUES (%s, %s, %s, %s) RETURNING id",
        ("u2@example.com", "x", True, False),
    ).fetchone()[0]
    
    agent_id = db.execute(
        "INSERT INTO agents (user_id, name, brokerage, email, phone, photo_filename) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
        (user_id, "Agent2", "Broker2", "a2@example.com", None, None),
    ).fetchone()[0]
    
    property_id = db.execute(
        "INSERT INTO properties (agent_id, address, beds, baths, sqft, price, description, slug, qr_code) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (agent_id, "456 Test Ave", "4", "3", "2000", "200000", "desc2", "slug2", "qr2"),
    ).fetchone()[0]

    from utils.storage import get_storage
    storage = get_storage()
    source_key = f"uploads/orders/order_test2.pdf"
    storage.put_file(b"%PDF-1.4\n%%EOF\n", source_key)

    order_id = db.execute(
        """INSERT INTO orders (user_id, property_id, sign_pdf_path, status, order_type, paid_at)
           VALUES (%s, %s, %s, 'paid', 'sign', NOW()) RETURNING id""",
        (user_id, property_id, source_key),
    ).fetchone()[0]
    db.commit()

    from services.fulfillment import fulfill_order

    # Call multiple times
    for _ in range(3):
        result = fulfill_order(order_id)
        assert result is True

    # Verify only one print job
    job_count = db.execute(
        "SELECT COUNT(*) FROM print_jobs WHERE order_id = %s", (order_id,)
    ).fetchone()[0]
    assert job_count == 1
