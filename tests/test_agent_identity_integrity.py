from werkzeug.security import generate_password_hash


def _register_payload(email: str, full_name: str = "Agent Person"):
    return {
        "full_name": full_name,
        "email": email,
        "password": "password123",
        "brokerage": "Integrity Realty",
        "phone": "555-0001",
    }


def _submit_payload(email: str, agent_name: str = "Agent Person"):
    return {
        "address": "101 Integrity Way",
        "beds": "3",
        "baths": "2",
        "agent_name": agent_name,
        "brokerage": "Integrity Realty",
        "email": email,
        "phone": "555-0001",
        "mode": "property_only",
    }


def test_register_does_not_create_duplicate_agent_row(client, db, monkeypatch):
    email_mixed = "X@Email.com"
    email_norm = "x@email.com"

    db.execute(
        "INSERT INTO agents (name, brokerage, email, user_id) VALUES (%s, %s, %s, NULL)",
        ("Legacy Agent", "Legacy Realty", email_mixed),
    )
    db.commit()

    monkeypatch.setattr("routes.auth.send_verification_email", lambda *_args, **_kwargs: True)

    resp = client.post("/register", data=_register_payload(email_norm), follow_redirects=True)
    assert resp.status_code == 200

    row = db.execute(
        """
        SELECT COUNT(*) AS cnt, MIN(user_id) AS min_user_id
        FROM agents
        WHERE lower(email) = %s
        """,
        (email_norm,),
    ).fetchone()
    assert int(row["cnt"]) == 1
    assert row["min_user_id"] is None


def test_submit_same_email_does_not_create_second_agent_row(client, db):
    email = "submit_same_email@example.com"
    pw_hash = generate_password_hash("password123")

    user_id = db.execute(
        """
        INSERT INTO users (email, password_hash, full_name, is_verified)
        VALUES (%s, %s, %s, %s)
        RETURNING id
        """,
        (email, pw_hash, "Submit User", True),
    ).fetchone()["id"]
    db.execute(
        """
        INSERT INTO agents (user_id, name, brokerage, email, phone)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (user_id, "Submit User", "Integrity Realty", email, "555-0001"),
    )
    db.commit()

    login_resp = client.post("/login", data={"email": email, "password": "password123"}, follow_redirects=True)
    assert login_resp.status_code == 200

    resp = client.post("/submit", data=_submit_payload(email, agent_name="Submit User"), follow_redirects=False)
    assert resp.status_code in {302, 303, 403}

    row = db.execute(
        "SELECT COUNT(*) AS cnt FROM agents WHERE lower(email) = %s",
        (email,),
    ).fetchone()
    assert int(row["cnt"]) == 1


def test_claim_conflict_user_b_cannot_take_user_a_agent(client, db):
    owner_email = "owner_identity@example.com"
    attacker_email = "attacker_identity@example.com"
    owner_hash = generate_password_hash("pw-owner")
    attacker_hash = generate_password_hash("pw-attacker")

    owner_id = db.execute(
        "INSERT INTO users (email, password_hash, is_verified) VALUES (%s, %s, %s) RETURNING id",
        (owner_email, owner_hash, True),
    ).fetchone()["id"]
    db.execute(
        "INSERT INTO users (email, password_hash, is_verified) VALUES (%s, %s, %s)",
        (attacker_email, attacker_hash, True),
    )
    db.execute(
        """
        INSERT INTO agents (user_id, name, brokerage, email, phone)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (owner_id, "Owner Agent", "Integrity Realty", owner_email, "555-0002"),
    )
    db.commit()

    login_resp = client.post("/login", data={"email": attacker_email, "password": "pw-attacker"}, follow_redirects=True)
    assert login_resp.status_code == 200

    resp = client.post("/submit", data=_submit_payload(owner_email, agent_name="Attacker"), follow_redirects=True)
    assert resp.status_code == 403
    assert "already claimed" in resp.get_data(as_text=True).lower()

    row = db.execute(
        "SELECT user_id, COUNT(*) OVER () AS total FROM agents WHERE lower(email) = %s LIMIT 1",
        (owner_email,),
    ).fetchone()
    assert int(row["total"]) == 1
    assert int(row["user_id"]) == int(owner_id)


def test_case_insensitive_email_maps_to_single_agent_identity(client, db, monkeypatch):
    mixed_email = "CaseSensitive@Example.com"
    normalized_email = "casesensitive@example.com"

    db.execute(
        "INSERT INTO agents (name, brokerage, email, user_id) VALUES (%s, %s, %s, NULL)",
        ("Case Agent", "Case Realty", mixed_email),
    )
    db.commit()

    monkeypatch.setattr("routes.auth.send_verification_email", lambda *_args, **_kwargs: True)
    monkeypatch.setattr("routes.auth.generate_verification_code", lambda: "333333")

    register_resp = client.post("/register", data=_register_payload(normalized_email, full_name="Case User"), follow_redirects=True)
    assert register_resp.status_code == 200

    user_row = db.execute(
        "SELECT id, verification_code FROM users WHERE lower(email) = %s",
        (normalized_email,),
    ).fetchone()
    assert user_row is not None
    assert user_row["verification_code"] == "333333"

    verify_resp = client.post("/verify", data={"code": "333333"}, follow_redirects=True)
    assert verify_resp.status_code == 200
    assert "email verified successfully" in verify_resp.get_data(as_text=True).lower()

    agent_row = db.execute(
        """
        SELECT COUNT(*) AS cnt, MIN(user_id) AS min_user_id, MIN(email) AS email_value
        FROM agents
        WHERE lower(email) = %s
        """,
        (normalized_email,),
    ).fetchone()

    assert int(agent_row["cnt"]) == 1
    assert int(agent_row["min_user_id"]) == int(user_row["id"])
    assert agent_row["email_value"] == normalized_email
