"""Regression checks for legacy routes and checkout safety guards."""


def _force_login(client, user_id):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True


def _create_verified_user(db, email="legacy@test.com"):
    row = db.execute(
        """
        INSERT INTO users (email, password_hash, is_verified)
        VALUES (%s, %s, true)
        RETURNING id
        """,
        (email, "x"),
    ).fetchone()
    db.commit()
    return row["id"]


def test_public_order_redirects_to_select_sign(client):
    resp = client.get("/order", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["Location"].endswith("/select-sign")


def test_legacy_smart_sign_urls_redirect_to_dashboard(client, db):
    user_id = _create_verified_user(db, email="legacy-smart@test.com")
    _force_login(client, user_id)

    root_resp = client.get("/smart-signs/", follow_redirects=False)
    manage_resp = client.get("/smart-signs/manage", follow_redirects=False)

    assert root_resp.status_code == 302
    assert manage_resp.status_code == 302
    assert root_resp.headers["Location"].endswith("/dashboard/#smart-signs-section")
    assert manage_resp.headers["Location"].endswith("/dashboard/#smart-signs-section")


def test_checkout_guard_blocks_payment_when_stripe_key_missing(client, app, db):
    user_id = _create_verified_user(db, email="stripe-guard@test.com")
    _force_login(client, user_id)

    order_id = db.execute(
        """
        INSERT INTO orders (
            user_id, status, order_type, print_product, material, print_size
        ) VALUES (
            %s, 'pending_payment', 'smart_sign', 'smart_sign', 'aluminum_040', '18x24'
        )
        RETURNING id
        """,
        (user_id,),
    ).fetchone()["id"]
    db.commit()

    original_key = app.config.get("STRIPE_SECRET_KEY")
    app.config["STRIPE_SECRET_KEY"] = None
    try:
        resp = client.post(
            f"/smart-signs/order/{order_id}/pay",
            data={},
            follow_redirects=True,
        )
    finally:
        app.config["STRIPE_SECRET_KEY"] = original_key

    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert "Checkout is unavailable" in html
