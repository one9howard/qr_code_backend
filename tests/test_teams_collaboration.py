import io
import re
from datetime import datetime, timedelta, timezone

import pytest
from werkzeug.security import generate_password_hash

from services.teams_collab import accept_invite
from services.team_files import cleanup_expired_team_files
from tests.factories import add_member, create_team


def _force_login(client, user_id):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True


def _create_user(db, email, password="password123", is_verified=True):
    row = db.execute(
        """
        INSERT INTO users (email, password_hash, is_verified, subscription_status)
        VALUES (%s, %s, %s, 'active')
        RETURNING id
        """,
        (email, generate_password_hash(password), is_verified),
    ).fetchone()
    db.commit()
    return row["id"]


def _create_agent(db, user_id, email, name="Agent"):
    row = db.execute(
        """
        INSERT INTO agents (user_id, name, brokerage, email, phone)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id
        """,
        (user_id, name, "Test Brokerage", email, "555-1111"),
    ).fetchone()
    db.commit()
    return row["id"]


def _create_property(db, agent_id, address, team_id=None):
    row = db.execute(
        """
        INSERT INTO properties (agent_id, team_id, address, beds, baths, slug, qr_code)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            agent_id,
            team_id,
            address,
            "3",
            "2",
            f"slug-{agent_id}-{abs(hash(address)) % 100000}",
            f"qr-{agent_id}-{abs(hash(address)) % 100000}",
        ),
    ).fetchone()
    db.commit()
    return row["id"]


def _insert_property_file(
    db,
    team_id,
    property_id,
    uploader_user_id,
    kind,
    storage_key,
    original_filename,
    expires_at=None,
):
    if expires_at is None:
        expires_at = datetime.now(timezone.utc) + timedelta(days=30)
    row = db.execute(
        """
        INSERT INTO property_files (
            team_id, property_id, uploader_user_id, kind, storage_key,
            original_filename, content_type, size_bytes, expires_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            team_id,
            property_id,
            uploader_user_id,
            kind,
            storage_key,
            original_filename,
            "text/csv" if kind == "export" else "application/pdf",
            10,
            expires_at,
        ),
    ).fetchone()
    db.commit()
    return row["id"]


def test_admin_create_team_assigns_owner_properties(client, db):
    owner_id = _create_user(db, "owner-create-team@example.com")
    owner_agent_id = _create_agent(db, owner_id, "owner-create-team@example.com")
    property_id = _create_property(db, owner_agent_id, "100 Team Start Ave", team_id=None)

    _force_login(client, owner_id)
    resp = client.post("/teams/create", data={"name": "Broker Team"}, follow_redirects=False)

    assert resp.status_code in {302, 303}
    match = re.search(r"/teams/(\d+)", resp.headers.get("Location", ""))
    assert match, "Expected redirect to /teams/<id>"
    team_id = int(match.group(1))

    member = db.execute(
        "SELECT role, status FROM team_members WHERE team_id = %s AND user_id = %s",
        (team_id, owner_id),
    ).fetchone()
    assert member is not None
    assert member["role"] == "admin"
    assert member["status"] == "active"

    prop = db.execute("SELECT team_id FROM properties WHERE id = %s", (property_id,)).fetchone()
    assert int(prop["team_id"]) == team_id


def test_viewer_permissions(client, db, monkeypatch):
    owner_id = _create_user(db, "owner-viewer@example.com")
    owner_agent_id = _create_agent(db, owner_id, "owner-viewer@example.com")
    team_id = create_team(db, owner_id)
    property_id = _create_property(db, owner_agent_id, "101 Viewer Ln", team_id=team_id)

    viewer_id = _create_user(db, "viewer@example.com")
    add_member(db, team_id, viewer_id, "viewer")

    export_file_id = _insert_property_file(
        db,
        team_id,
        property_id,
        owner_id,
        "export",
        "teams/export.csv",
        "export.csv",
    )
    upload_file_id = _insert_property_file(
        db,
        team_id,
        property_id,
        owner_id,
        "upload",
        "teams/upload.pdf",
        "upload.pdf",
    )

    class MockStorage:
        def get_file(self, _key):
            return io.BytesIO(b"content")

    monkeypatch.setattr("services.team_files.get_storage", lambda: MockStorage())

    _force_login(client, viewer_id)

    assert client.get(f"/teams/{team_id}").status_code == 200
    assert client.get(f"/teams/{team_id}/properties/{property_id}").status_code == 200
    assert client.post(f"/teams/{team_id}/properties/{property_id}/comments", data={"body": "not allowed"}).status_code == 403
    assert (
        client.post(
            f"/teams/{team_id}/properties/{property_id}/files/upload",
            data={"file": (io.BytesIO(b"abc"), "note.pdf")},
            content_type="multipart/form-data",
        ).status_code
        == 403
    )
    assert client.get(f"/teams/{team_id}/files/{export_file_id}/download").status_code == 200
    assert client.get(f"/teams/{team_id}/files/{upload_file_id}/download").status_code == 403


def test_member_permissions(client, db, monkeypatch):
    owner_id = _create_user(db, "owner-member@example.com")
    owner_agent_id = _create_agent(db, owner_id, "owner-member@example.com")
    team_id = create_team(db, owner_id)
    property_id = _create_property(db, owner_agent_id, "102 Member Rd", team_id=team_id)

    member_id = _create_user(db, "member@example.com")
    add_member(db, team_id, member_id, "member")

    class MockStorage:
        def __init__(self):
            self.deleted = []

        def put_file(self, *_args, **_kwargs):
            return True

        def get_file(self, _key):
            return io.BytesIO(b"download")

        def exists(self, _key):
            return True

        def delete(self, key):
            self.deleted.append(key)

    storage = MockStorage()
    monkeypatch.setattr("services.team_files.get_storage", lambda: storage)

    _force_login(client, member_id)

    comment_resp = client.post(
        f"/teams/{team_id}/properties/{property_id}/comments",
        data={"body": "Member comment"},
        follow_redirects=False,
    )
    assert comment_resp.status_code in {302, 303}

    upload_resp = client.post(
        f"/teams/{team_id}/properties/{property_id}/files/upload",
        data={"file": (io.BytesIO(b"%PDF"), "workspace.pdf")},
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert upload_resp.status_code in {302, 303}

    export_resp = client.post(
        f"/teams/{team_id}/properties/{property_id}/files/export-leads",
        follow_redirects=False,
    )
    assert export_resp.status_code in {302, 303}

    uploaded = db.execute(
        """
        SELECT id FROM property_files
        WHERE team_id = %s AND property_id = %s AND kind = 'upload' AND deleted_at IS NULL
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (team_id, property_id),
    ).fetchone()
    exported = db.execute(
        """
        SELECT id FROM property_files
        WHERE team_id = %s AND property_id = %s AND kind = 'export' AND deleted_at IS NULL
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (team_id, property_id),
    ).fetchone()
    assert uploaded is not None
    assert exported is not None

    assert client.get(f"/teams/{team_id}/files/{uploaded['id']}/download").status_code == 200
    assert client.get(f"/teams/{team_id}/files/{exported['id']}/download").status_code == 200
    assert client.get(f"/teams/{team_id}/settings").status_code == 403


def test_admin_permissions_retention_invite_delete(client, db, monkeypatch):
    owner_id = _create_user(db, "owner-admin@example.com")
    owner_agent_id = _create_agent(db, owner_id, "owner-admin@example.com")
    team_id = create_team(db, owner_id)
    property_id = _create_property(db, owner_agent_id, "103 Admin Ct", team_id=team_id)

    class MockStorage:
        def __init__(self):
            self.deleted = []

        def exists(self, _key):
            return True

        def delete(self, key):
            self.deleted.append(key)

    storage = MockStorage()
    monkeypatch.setattr("services.team_files.get_storage", lambda: storage)

    _force_login(client, owner_id)

    retention_resp = client.post(
        f"/teams/{team_id}/settings",
        data={"action": "set_retention", "retention_days": "90"},
        follow_redirects=False,
    )
    assert retention_resp.status_code in {302, 303, 200}
    retention = db.execute("SELECT retention_days FROM teams WHERE id = %s", (team_id,)).fetchone()
    assert int(retention["retention_days"]) == 90

    invitee_email = "invitee@example.com"
    invitee_id = _create_user(db, invitee_email)
    invite_resp = client.post(
        f"/teams/{team_id}/settings",
        data={"action": "invite_member", "email": invitee_email, "role": "member"},
        follow_redirects=False,
    )
    assert invite_resp.status_code in {302, 303, 200}
    invite = db.execute(
        "SELECT id, token, accepted_at FROM team_invites WHERE team_id = %s AND email = %s ORDER BY id DESC LIMIT 1",
        (team_id, invitee_email),
    ).fetchone()
    assert invite is not None
    assert invite["accepted_at"] is None

    accepted_team_id = accept_invite(invite["token"], invitee_id)
    assert accepted_team_id == team_id
    member = db.execute(
        "SELECT role, status FROM team_members WHERE team_id = %s AND user_id = %s",
        (team_id, invitee_id),
    ).fetchone()
    assert member is not None
    assert member["status"] == "active"

    mismatch_token = db.execute(
        """
        INSERT INTO team_invites (team_id, email, role, token, invited_by_user_id, expires_at)
        VALUES (%s, %s, 'viewer', %s, %s, NOW() + INTERVAL '7 days')
        RETURNING token
        """,
        (team_id, "different@example.com", "token-mismatch-123", owner_id),
    ).fetchone()["token"]
    other_id = _create_user(db, "other-user@example.com")
    with pytest.raises(PermissionError):
        accept_invite(mismatch_token, other_id)

    _force_login(client, owner_id)
    file_id = _insert_property_file(
        db,
        team_id,
        property_id,
        owner_id,
        "upload",
        "teams/delete_me.pdf",
        "delete_me.pdf",
    )
    delete_resp = client.post(f"/teams/{team_id}/files/{file_id}/delete", follow_redirects=False)
    assert delete_resp.status_code in {302, 303}
    deleted = db.execute("SELECT deleted_at FROM property_files WHERE id = %s", (file_id,)).fetchone()
    assert deleted["deleted_at"] is not None
    assert "teams/delete_me.pdf" in storage.deleted


def test_cleanup_expired_team_files_marks_deleted_and_calls_storage(db, monkeypatch):
    owner_id = _create_user(db, "owner-cleanup@example.com")
    owner_agent_id = _create_agent(db, owner_id, "owner-cleanup@example.com")
    team_id = create_team(db, owner_id)
    property_id = _create_property(db, owner_agent_id, "104 Cleanup Way", team_id=team_id)

    expired_id = _insert_property_file(
        db,
        team_id,
        property_id,
        owner_id,
        "upload",
        "teams/expired.pdf",
        "expired.pdf",
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
    )

    class MockStorage:
        def __init__(self):
            self.deleted = []

        def exists(self, _key):
            return True

        def delete(self, key):
            self.deleted.append(key)

    storage = MockStorage()
    monkeypatch.setattr("services.team_files.get_storage", lambda: storage)

    deleted_count = cleanup_expired_team_files(dry_run=False)
    assert deleted_count == 1

    row = db.execute("SELECT deleted_at FROM property_files WHERE id = %s", (expired_id,)).fetchone()
    assert row["deleted_at"] is not None
    assert "teams/expired.pdf" in storage.deleted
