"""
Agent identity helpers.

Enforces a single case-insensitive email identity and explicit verified claim flow.
"""

from __future__ import annotations

from typing import Any


def normalize_agent_email(email: str | None) -> str:
    return (email or "").strip().lower()


def get_agent_by_normalized_email(db: Any, normalized_email: str):
    return db.execute(
        """
        SELECT id, user_id, email, name, brokerage, phone, photo_filename, logo_filename, scheduling_url
        FROM agents
        WHERE lower(email) = %s
        LIMIT 1
        """,
        (normalized_email,),
    ).fetchone()


def claim_agent_for_verified_user(db: Any, user_id: int, email: str, default_name: str | None = None) -> dict:
    """
    Claim (or create+claim) the agent identity for a verified user.

    Rules:
    - user must exist and be verified
    - claim email must match user's verified email (case-insensitive)
    - claimed by another user => deny
    - unclaimed => claim
    - absent => create claimed row
    """
    normalized_email = normalize_agent_email(email)
    if not normalized_email:
        raise ValueError("Agent email is required.")

    user = db.execute(
        "SELECT id, email, is_verified, full_name FROM users WHERE id = %s",
        (user_id,),
    ).fetchone()
    if not user:
        raise PermissionError("User not found.")
    if not bool(user["is_verified"]):
        raise PermissionError("Email verification is required before claiming an agent profile.")

    user_email = normalize_agent_email(user["email"])
    if user_email != normalized_email:
        raise PermissionError("You can only claim an agent profile for your verified account email.")

    agent = get_agent_by_normalized_email(db, normalized_email)
    if agent:
        if agent["user_id"] is None:
            db.execute(
                "UPDATE agents SET user_id = %s, email = %s WHERE id = %s",
                (user_id, normalized_email, agent["id"]),
            )
            return {"agent_id": agent["id"], "status": "claimed"}
        if int(agent["user_id"]) == int(user_id):
            return {"agent_id": agent["id"], "status": "already_claimed"}
        raise PermissionError("This agent email is already claimed by another account.")

    agent_name = (default_name or user.get("full_name") or normalized_email.split("@")[0]).strip() or "Agent"
    created = db.execute(
        """
        INSERT INTO agents (user_id, name, brokerage, email, phone, photo_filename, logo_filename)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (user_id, agent_name, "", normalized_email, None, None, None),
    ).fetchone()
    return {"agent_id": created["id"], "status": "created_and_claimed"}

