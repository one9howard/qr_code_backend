import csv
import io
import logging
import os
from datetime import datetime, timezone, timedelta
from uuid import uuid4

from flask import send_file
from werkzeug.utils import secure_filename

from database import get_db
from utils.storage import get_storage
from services.teams_collab import log_audit_event

logger = logging.getLogger(__name__)

ALLOWED_UPLOAD_EXTENSIONS = {".csv", ".pdf", ".png", ".jpg", ".jpeg"}


def _csv_safe(value):
    if value is None:
        return ""
    text = str(value)
    if text.startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def _team_retention_days(db, team_id):
    row = db.execute("SELECT retention_days FROM teams WHERE id = %s", (team_id,)).fetchone()
    if not row:
        raise ValueError("Team not found.")
    return int(row["retention_days"])


def list_files(team_id, property_id):
    db = get_db()
    return db.execute(
        """
        SELECT
            id, team_id, property_id, uploader_user_id, kind, storage_key,
            original_filename, content_type, size_bytes, created_at, expires_at, deleted_at
        FROM property_files
        WHERE team_id = %s
          AND property_id = %s
          AND deleted_at IS NULL
        ORDER BY created_at DESC
        """,
        (team_id, property_id),
    ).fetchall()


def upload_file(team_id, property_id, uploader_user_id, upload, kind="upload"):
    if kind != "upload":
        raise ValueError("Upload endpoint only supports kind='upload'.")
    if upload is None or not getattr(upload, "filename", ""):
        raise ValueError("A file is required.")

    safe_filename = secure_filename(upload.filename)
    if not safe_filename:
        raise ValueError("Invalid filename.")

    extension = os.path.splitext(safe_filename)[1].lower()
    if extension not in ALLOWED_UPLOAD_EXTENSIONS:
        raise ValueError("Unsupported file type.")

    db = get_db()
    retention_days = _team_retention_days(db, team_id)
    expires_at = datetime.now(timezone.utc) + timedelta(days=retention_days)

    storage_key = (
        f"teams/{team_id}/properties/{property_id}/upload/"
        f"{uuid4().hex}_{safe_filename}"
    )

    storage = get_storage()
    content_type = upload.content_type or "application/octet-stream"
    storage.put_file(upload, storage_key, content_type=content_type)

    size_bytes = upload.content_length
    row = db.execute(
        """
        INSERT INTO property_files (
            team_id, property_id, uploader_user_id, kind, storage_key,
            original_filename, content_type, size_bytes, expires_at
        )
        VALUES (%s, %s, %s, 'upload', %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            team_id,
            property_id,
            uploader_user_id,
            storage_key,
            safe_filename,
            content_type,
            size_bytes,
            expires_at,
        ),
    ).fetchone()

    log_audit_event(
        db,
        team_id=team_id,
        actor_user_id=uploader_user_id,
        event_type="file.uploaded",
        object_type="property_files",
        object_id=row["id"],
        metadata={"property_id": property_id, "kind": "upload"},
    )
    db.commit()
    return row["id"]


def generate_leads_export(team_id, property_id, actor_user_id):
    db = get_db()
    retention_days = _team_retention_days(db, team_id)
    expires_at = datetime.now(timezone.utc) + timedelta(days=retention_days)

    leads = db.execute(
        """
        SELECT
            id, buyer_name, buyer_email, buyer_phone, status, created_at, message
        FROM leads
        WHERE property_id = %s
        ORDER BY created_at DESC
        """,
        (property_id,),
    ).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["lead_id", "buyer_name", "buyer_email", "buyer_phone", "status", "created_at", "message"])

    for lead in leads:
        writer.writerow(
            [
                _csv_safe(lead["id"]),
                _csv_safe(lead["buyer_name"]),
                _csv_safe(lead["buyer_email"]),
                _csv_safe(lead["buyer_phone"]),
                _csv_safe(lead["status"]),
                _csv_safe(lead["created_at"]),
                _csv_safe(lead["message"]),
            ]
        )

    csv_bytes = output.getvalue().encode("utf-8")
    output.close()

    filename = f"leads_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    storage_key = (
        f"teams/{team_id}/properties/{property_id}/export/"
        f"{uuid4().hex}_{filename}"
    )

    storage = get_storage()
    storage.put_file(io.BytesIO(csv_bytes), storage_key, content_type="text/csv")

    row = db.execute(
        """
        INSERT INTO property_files (
            team_id, property_id, uploader_user_id, kind, storage_key,
            original_filename, content_type, size_bytes, expires_at
        )
        VALUES (%s, %s, %s, 'export', %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            team_id,
            property_id,
            actor_user_id,
            storage_key,
            filename,
            "text/csv",
            len(csv_bytes),
            expires_at,
        ),
    ).fetchone()

    log_audit_event(
        db,
        team_id=team_id,
        actor_user_id=actor_user_id,
        event_type="leads.exported",
        object_type="property_files",
        object_id=row["id"],
        metadata={"property_id": property_id, "lead_count": len(leads)},
    )
    db.commit()
    return row["id"]


def stream_download(team_id, file_id, actor_user_id, role):
    db = get_db()
    row = db.execute(
        """
        SELECT
            id, team_id, property_id, uploader_user_id, kind, storage_key,
            original_filename, content_type, size_bytes, created_at, expires_at, deleted_at
        FROM property_files
        WHERE team_id = %s AND id = %s AND deleted_at IS NULL
        LIMIT 1
        """,
        (team_id, file_id),
    ).fetchone()
    if not row:
        raise FileNotFoundError("File not found.")

    if role == "viewer" and row["kind"] != "export":
        raise PermissionError("Viewers can only download export files.")

    storage = get_storage()
    payload = storage.get_file(row["storage_key"])

    log_audit_event(
        db,
        team_id=team_id,
        actor_user_id=actor_user_id,
        event_type="file.downloaded",
        object_type="property_files",
        object_id=row["id"],
        metadata={"property_id": row["property_id"], "kind": row["kind"]},
    )
    db.commit()

    mimetype = row["content_type"] or "application/octet-stream"
    return send_file(
        payload,
        as_attachment=True,
        download_name=row["original_filename"],
        mimetype=mimetype,
    )


def delete_file(team_id, file_id, actor_user_id):
    db = get_db()
    row = db.execute(
        """
        SELECT
            id, team_id, property_id, kind, storage_key, deleted_at
        FROM property_files
        WHERE team_id = %s AND id = %s
        LIMIT 1
        """,
        (team_id, file_id),
    ).fetchone()
    if not row:
        raise FileNotFoundError("File not found.")
    if row["deleted_at"] is not None:
        return row

    storage = get_storage()
    try:
        if storage.exists(row["storage_key"]):
            storage.delete(row["storage_key"])
    except Exception as exc:
        logger.warning("[TeamFiles] Storage delete failed for file_id=%s: %s", row["id"], type(exc).__name__)

    deleted_at = datetime.now(timezone.utc)
    db.execute(
        "UPDATE property_files SET deleted_at = %s WHERE id = %s",
        (deleted_at, row["id"]),
    )
    log_audit_event(
        db,
        team_id=team_id,
        actor_user_id=actor_user_id,
        event_type="file.deleted",
        object_type="property_files",
        object_id=row["id"],
        metadata={"property_id": row["property_id"], "kind": row["kind"]},
    )
    db.commit()
    return row


def cleanup_expired_team_files(dry_run=False):
    db = get_db()
    now = datetime.now(timezone.utc)
    rows = db.execute(
        """
        SELECT id, team_id, property_id, kind, storage_key
        FROM property_files
        WHERE deleted_at IS NULL
          AND expires_at < %s
        ORDER BY expires_at ASC
        """,
        (now,),
    ).fetchall()

    if dry_run:
        return len(rows)

    storage = get_storage()
    deleted_count = 0
    for row in rows:
        try:
            if storage.exists(row["storage_key"]):
                storage.delete(row["storage_key"])
        except Exception as exc:
            logger.warning("[TeamFiles] Cleanup storage delete failed for file_id=%s: %s", row["id"], type(exc).__name__)

        db.execute(
            "UPDATE property_files SET deleted_at = %s WHERE id = %s",
            (now, row["id"]),
        )
        log_audit_event(
            db,
            team_id=row["team_id"],
            actor_user_id=None,
            event_type="cleanup.file_deleted",
            object_type="property_files",
            object_id=row["id"],
            metadata={"property_id": row["property_id"], "kind": row["kind"]},
        )
        deleted_count += 1

    db.commit()
    return deleted_count
