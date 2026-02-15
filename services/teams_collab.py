import logging
import secrets
from datetime import datetime, timedelta, timezone

from flask import has_request_context, request
from psycopg2.extras import Json

from database import get_db

logger = logging.getLogger(__name__)


ROLE_ORDER = {"viewer": 1, "member": 2, "admin": 3}
ACTIVE_STATUS = "active"


def normalize_email(email):
    return (email or "").strip().lower()


def _request_meta():
    if not has_request_context():
        return None, None
    return request.remote_addr, request.user_agent.string if request.user_agent else None


def log_audit_event(
    db,
    team_id,
    actor_user_id,
    event_type,
    object_type=None,
    object_id=None,
    metadata=None,
    ip=None,
    user_agent=None,
):
    if ip is None or user_agent is None:
        req_ip, req_user_agent = _request_meta()
        ip = ip if ip is not None else req_ip
        user_agent = user_agent if user_agent is not None else req_user_agent

    db.execute(
        """
        INSERT INTO audit_events (
            team_id, actor_user_id, event_type, object_type, object_id, ip, user_agent, metadata
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            team_id,
            actor_user_id,
            event_type,
            object_type,
            object_id,
            ip,
            user_agent,
            Json(metadata) if metadata is not None else None,
        ),
    )


def _get_membership(db, team_id, user_id):
    return db.execute(
        """
        SELECT id, team_id, user_id, role, status, created_at
        FROM team_members
        WHERE team_id = %s AND user_id = %s
        LIMIT 1
        """,
        (team_id, user_id),
    ).fetchone()


def create_team(owner_user_id, name):
    db = get_db()
    clean_name = (name or "").strip()
    if not clean_name:
        raise ValueError("Team name is required.")

    team_row = db.execute(
        """
        INSERT INTO teams (name, owner_user_id, retention_days)
        VALUES (%s, %s, 60)
        RETURNING id
        """,
        (clean_name, owner_user_id),
    ).fetchone()
    team_id = team_row["id"]

    db.execute(
        """
        INSERT INTO team_members (team_id, user_id, role, status)
        VALUES (%s, %s, 'admin', %s)
        """,
        (team_id, owner_user_id, ACTIVE_STATUS),
    )

    # Auto-assign owner's existing properties that are still unassigned.
    db.execute(
        """
        UPDATE properties
        SET team_id = %s
        WHERE team_id IS NULL
          AND agent_id IN (
            SELECT id FROM agents WHERE user_id = %s
          )
        """,
        (team_id, owner_user_id),
    )

    log_audit_event(
        db,
        team_id=team_id,
        actor_user_id=owner_user_id,
        event_type="team.created",
        object_type="team",
        object_id=team_id,
    )
    db.commit()
    return team_id


def get_user_teams(user_id):
    db = get_db()
    return db.execute(
        """
        SELECT
            t.id,
            t.name,
            t.owner_user_id,
            t.retention_days,
            t.created_at,
            tm.role,
            tm.status
        FROM team_members tm
        JOIN teams t ON t.id = tm.team_id
        WHERE tm.user_id = %s AND tm.status = %s
        ORDER BY t.created_at DESC
        """,
        (user_id, ACTIVE_STATUS),
    ).fetchall()


def get_team(team_id):
    db = get_db()
    return db.execute(
        """
        SELECT id, name, owner_user_id, retention_days, created_at
        FROM teams
        WHERE id = %s
        LIMIT 1
        """,
        (team_id,),
    ).fetchone()


def require_team_role(team_id, user_id, min_role):
    if min_role not in ROLE_ORDER:
        raise ValueError("Unknown role requirement.")

    db = get_db()
    membership = _get_membership(db, team_id, user_id)
    if not membership or membership["status"] != ACTIVE_STATUS:
        raise PermissionError("You are not an active member of this team.")

    member_role = membership["role"]
    if ROLE_ORDER.get(member_role, 0) < ROLE_ORDER[min_role]:
        raise PermissionError("You do not have permission for this action.")

    return membership


def invite_member(team_id, inviter_user_id, email, role):
    if role not in {"viewer", "member"}:
        raise ValueError("Invalid role for invite.")

    db = get_db()
    require_team_role(team_id, inviter_user_id, "admin")

    clean_email = normalize_email(email)
    if not clean_email:
        raise ValueError("Invite email is required.")

    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)

    invite = db.execute(
        """
        INSERT INTO team_invites (team_id, email, role, token, invited_by_user_id, expires_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (team_id, clean_email, role, token, inviter_user_id, expires_at),
    ).fetchone()

    log_audit_event(
        db,
        team_id=team_id,
        actor_user_id=inviter_user_id,
        event_type="member.invited",
        object_type="team_invites",
        object_id=invite["id"],
        metadata={"role": role},
    )
    db.commit()
    return token


def accept_invite(token, user_id):
    db = get_db()
    now = datetime.now(timezone.utc)
    invite = db.execute(
        """
        SELECT id, team_id, email, role, token, expires_at, accepted_at
        FROM team_invites
        WHERE token = %s
        LIMIT 1
        """,
        (token,),
    ).fetchone()
    if not invite:
        raise ValueError("Invite not found.")
    if invite["accepted_at"] is not None:
        raise ValueError("Invite already accepted.")
    if invite["expires_at"] and invite["expires_at"] < now:
        raise ValueError("Invite has expired.")

    user = db.execute("SELECT id, email FROM users WHERE id = %s", (user_id,)).fetchone()
    if not user:
        raise ValueError("User not found.")

    if normalize_email(user["email"]) != normalize_email(invite["email"]):
        raise PermissionError("Invite email does not match your account.")

    existing_member = _get_membership(db, invite["team_id"], user_id)
    if existing_member:
        if existing_member["status"] != ACTIVE_STATUS:
            db.execute(
                """
                UPDATE team_members
                SET status = %s, role = CASE WHEN role = 'admin' THEN role ELSE %s END
                WHERE id = %s
                """,
                (ACTIVE_STATUS, invite["role"], existing_member["id"]),
            )
    else:
        db.execute(
            """
            INSERT INTO team_members (team_id, user_id, role, status)
            VALUES (%s, %s, %s, %s)
            """,
            (invite["team_id"], user_id, invite["role"], ACTIVE_STATUS),
        )

    db.execute(
        "UPDATE team_invites SET accepted_at = %s WHERE id = %s",
        (now, invite["id"]),
    )

    # Auto-assign invitee's properties that are still unassigned.
    db.execute(
        """
        UPDATE properties
        SET team_id = %s
        WHERE team_id IS NULL
          AND agent_id IN (
            SELECT id FROM agents WHERE user_id = %s
          )
        """,
        (invite["team_id"], user_id),
    )

    log_audit_event(
        db,
        team_id=invite["team_id"],
        actor_user_id=user_id,
        event_type="member.added",
        object_type="team_members",
        metadata={"invite_id": invite["id"]},
    )
    db.commit()
    return invite["team_id"]


def set_retention_days(team_id, admin_user_id, days):
    try:
        retention_days = int(days)
    except (TypeError, ValueError):
        raise ValueError("Retention days must be an integer.") from None

    if retention_days < 7 or retention_days > 365:
        raise ValueError("Retention days must be between 7 and 365.")

    db = get_db()
    require_team_role(team_id, admin_user_id, "admin")
    db.execute(
        "UPDATE teams SET retention_days = %s WHERE id = %s",
        (retention_days, team_id),
    )
    log_audit_event(
        db,
        team_id=team_id,
        actor_user_id=admin_user_id,
        event_type="retention.updated",
        object_type="teams",
        object_id=team_id,
        metadata={"retention_days": retention_days},
    )
    db.commit()
    return retention_days


def get_team_members(team_id):
    db = get_db()
    return db.execute(
        """
        SELECT
            tm.id,
            tm.team_id,
            tm.user_id,
            tm.role,
            tm.status,
            tm.created_at,
            u.email,
            u.full_name
        FROM team_members tm
        JOIN users u ON u.id = tm.user_id
        WHERE tm.team_id = %s
        ORDER BY tm.created_at ASC
        """,
        (team_id,),
    ).fetchall()


def get_team_invites(team_id):
    db = get_db()
    return db.execute(
        """
        SELECT
            id, team_id, email, role, token, invited_by_user_id, expires_at, accepted_at, created_at
        FROM team_invites
        WHERE team_id = %s
        ORDER BY created_at DESC
        """,
        (team_id,),
    ).fetchall()
