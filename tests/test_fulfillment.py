
def test_fulfill_order_enqueues_one_print_job(db, app):
    # Minimal user -> agent -> property -> order
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
        (agent_id, "123 Test St", "3", "2", "1000", "$1", "desc", "slug", "qr1"),
    ).fetchone()[0]

    # Source PDF set up using get_storage to align with app's config
    from utils.storage import get_storage
    storage = get_storage()
    source_key = "uploads/orders/order_1.pdf"
    storage.put_file(b"%PDF-1.4\n%%EOF\n", source_key)

    order_id = db.execute(
        """INSERT INTO orders (user_id, property_id, sign_pdf_path, status, order_type)
           VALUES (%s, %s, %s, 'paid', 'sign') RETURNING id""",
        (user_id, property_id, source_key),
    ).fetchone()[0]
    db.commit()

    from services.fulfillment import fulfill_order

    ok1 = fulfill_order(order_id)
    ok2 = fulfill_order(order_id)

    assert ok1 is True
    assert ok2 is True

    row = db.execute("SELECT COUNT(*) FROM print_jobs WHERE idempotency_key = %s", (f"order_{order_id}",)).fetchone()
    assert row[0] == 1
