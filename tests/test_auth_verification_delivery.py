from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash


def test_register_blocks_when_verification_email_fails_in_secure_stage(client, db, monkeypatch):
    monkeypatch.setattr("routes.auth._is_secure_stage", lambda: True)
    monkeypatch.setattr("routes.auth.send_verification_email", lambda *_args, **_kwargs: False)
    monkeypatch.setattr("routes.auth.generate_verification_code", lambda: "111111")

    resp = client.post(
        "/register",
        data={
            "full_name": "Secure Stage User",
            "email": "secure_stage_user@example.com",
            "password": "password123",
            "brokerage": "Acme Realty",
            "phone": "555-1010",
        },
        follow_redirects=True,
    )
    body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert "registration was not completed" in body.lower()
    user = db.execute(
        "SELECT id FROM users WHERE email = %s",
        ("secure_stage_user@example.com",),
    ).fetchone()
    agent = db.execute(
        "SELECT id FROM agents WHERE email = %s",
        ("secure_stage_user@example.com",),
    ).fetchone()
    assert user is None
    assert agent is None


def test_register_exposes_debug_code_in_dev_test_when_email_fails(client, db, monkeypatch):
    monkeypatch.setattr("routes.auth._is_secure_stage", lambda: False)
    monkeypatch.setattr("routes.auth._debug_verification_code_enabled", lambda: True)
    monkeypatch.setattr("routes.auth.send_verification_email", lambda *_args, **_kwargs: False)
    monkeypatch.setattr("routes.auth.generate_verification_code", lambda: "222222")

    resp = client.post(
        "/register",
        data={
            "full_name": "Debug OTP User",
            "email": "debug_otp_user@example.com",
            "password": "password123",
            "brokerage": "Acme Realty",
            "phone": "555-2020",
        },
        follow_redirects=True,
    )
    body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert "verification code: 222222" in body.lower()
    user = db.execute(
        "SELECT email, is_verified, verification_code FROM users WHERE email = %s",
        ("debug_otp_user@example.com",),
    ).fetchone()
    assert user is not None
    assert bool(user["is_verified"]) is False
    assert user["verification_code"] == "222222"


def test_resend_verification_rolls_back_on_email_failure_in_secure_stage(client, db, monkeypatch):
    email = "resend_secure_stage@example.com"
    password = "password123"
    old_code = "999999"

    cursor = db.execute(
        """
        INSERT INTO users (email, password_hash, full_name, is_verified, verification_code, verification_code_expires_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            email,
            generate_password_hash(password),
            "Resend User",
            False,
            old_code,
            datetime.now() + timedelta(minutes=15),
        ),
    )
    user_id = cursor.fetchone()["id"]
    db.commit()

    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True

    monkeypatch.setattr("routes.auth._is_secure_stage", lambda: True)
    monkeypatch.setattr("routes.auth.send_verification_email", lambda *_args, **_kwargs: False)
    monkeypatch.setattr("routes.auth.generate_verification_code", lambda: "123123")

    resp = client.get("/resend-verification", follow_redirects=True)
    body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert "could not resend your verification code" in body.lower()
    user = db.execute(
        "SELECT verification_code FROM users WHERE email = %s",
        (email,),
    ).fetchone()
    assert user["verification_code"] == old_code
