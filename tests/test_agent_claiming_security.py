
import pytest
from flask import session
from werkzeug.security import generate_password_hash

def test_register_does_not_link_agent_before_verification(client, db):
    """
    VULNERABILITY CHECK:
    An unverified user should NOT carry the 'user_id' link to an existing agent row just by registering.
    """
    email = "victim@example.com"
    
    # 0. Create an unclaimed agent
    db.execute(
        "INSERT INTO agents (name, email, brokerage, user_id) VALUES (%s, %s, %s, NULL)",
        ("Victim Agent", email, "Victim Realty")
    )
    db.commit()
    
    # 1. Register a user with that email
    resp = client.post("/register", data={
        "full_name": "Victim User",
        "email": email,
        "password": "password123",
        "brokerage": "Victim Realty",
        "phone": "555-1234"
    }, follow_redirects=True)
    assert resp.status_code == 200
    
    # 2. Check agent status
    # EXPECTED SECURITY BEHAVIOR: user_id is STILL NULL
    # CURRENT VULNERABLE BEHAVIOR: user_id is SET (test will fail until patched)
    agent = db.execute("SELECT user_id FROM agents WHERE email=%s", (email,)).fetchone()
    assert agent['user_id'] is None, "SECURITY FAIL: Agent linked prematurely on registration!"

def test_login_unverified_does_not_link_agent(client, db):
    """
    An existing unverified user logging in should NOT trigger agent linking.
    """
    email = "unverified@example.com"
    
    # 0. Create user (unverified) and unclaimed agent
    hashed = generate_password_hash("password123")
    db.execute(
        "INSERT INTO users (email, password_hash, full_name, is_verified) VALUES (%s, %s, %s, %s)",
        (email, hashed, "Unverified User", False)
    )
    db.execute(
        "INSERT INTO agents (name, email, brokerage, user_id) VALUES (%s, %s, %s, NULL)",
        ("Unverified Agent", email, "Some Realty")
    )
    db.commit()
    
    # 1. Login
    resp = client.post("/login", data={
        "email": email,
        "password": "password123"
    }, follow_redirects=True)
    assert resp.status_code == 200
    
    # 2. Check agent status
    agent = db.execute("SELECT user_id FROM agents WHERE email=%s", (email,)).fetchone()
    assert agent['user_id'] is None, "SECURITY FAIL: Unverified login linked agent!"

def test_verify_email_links_agent(client, db):
    """
    The only valid time to link an unclaimed agent is AFTER verification.
    """
    email = "legit@example.com"
    code = "123456"
    
    # 0. Create user (unverified) and unclaimed agent
    hashed = generate_password_hash("password123")
    db.execute(
        "INSERT INTO users (email, password_hash, full_name, is_verified, verification_code) VALUES (%s, %s, %s, %s, %s)",
        (email, hashed, "Legit User", False, code)
    )
    db.execute(
        "INSERT INTO agents (name, email, brokerage, user_id) VALUES (%s, %s, %s, NULL)",
        ("Legit Agent", email, "Legit Realty")
    )
    db.commit()
    
    # 1. Login first (required for /verify)
    client.post("/login", data={"email": email, "password": "password123"})
    
    # 2. Verify
    resp = client.post("/verify", data={"code": code}, follow_redirects=True)
    assert resp.status_code == 200
    assert "Email verified successfully" in resp.get_data(as_text=True)
    
    # 3. Check agent status -> MUST BE LINKED NOW
    user = db.execute("SELECT id FROM users WHERE email=%s", (email,)).fetchone()
    agent = db.execute("SELECT user_id FROM agents WHERE email=%s", (email,)).fetchone()
    
    assert agent['user_id'] is not None, "Agent not linked after verification!"
    assert agent['user_id'] == user['id'], "Agent linked to wrong user!"

def test_submit_cannot_claim_other_email(client, db):
    """
    Logged-in attacker submitting an agent email that IS NOT THEIRS should NOT claim it.
    """
    attacker_email = "attacker@example.com"
    victim_email = "victim@example.com"
    
    # 0. Create attacker (verified) and victim agent (unclaimed)
    hashed = generate_password_hash("password123")
    db.execute(
        "INSERT INTO users (email, password_hash, full_name, is_verified) VALUES (%s, %s, %s, %s)",
        (attacker_email, hashed, "Attacker", True)
    )
    db.execute(
        "INSERT INTO agents (name, email, brokerage, user_id) VALUES (%s, %s, %s, NULL)",
        ("Victim Agent", victim_email, "Victim Realty")
    )
    db.commit()
    
    # 1. Login as attacker
    client.post("/login", data={"email": attacker_email, "password": "password123"})
    
    # 2. Submit property using Victim's email
    resp = client.post("/submit", data={
        "address": "123 Attack St",
        "beds": "3",
        "baths": "2",
        "agent_name": "Victim Agent",
        "brokerage": "Victim Realty",
        "email": victim_email, # TARGET
        "phone": "555-6666"
    }, follow_redirects=True)
    
    # 3. Check Victim Agent logic
    # The vulnerability is that /submit implicitly claims logic if user is authenticated
    agent = db.execute("SELECT user_id FROM agents WHERE email=%s", (victim_email,)).fetchone()
    assert agent['user_id'] is None, "SECURITY FAIL: Attacker claimed victim agent via /submit!"
    
    # Either the flow blocks with 403 or allows submit flow but without ownership transfer.
    assert resp.status_code in {200, 302, 303, 403}, (
        f"Unexpected response status for submit flow: {resp.status_code}"
    )

