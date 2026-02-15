import logging

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from database import get_db
from services.team_files import (
    delete_file as delete_team_file,
    generate_leads_export,
    list_files,
    stream_download,
    upload_file,
)
from services.teams_collab import (
    accept_invite,
    create_team,
    get_team,
    get_team_invites,
    get_team_members,
    get_user_teams,
    invite_member,
    log_audit_event,
    require_team_role,
    set_retention_days,
)

logger = logging.getLogger(__name__)

teams_bp = Blueprint("teams", __name__, url_prefix="/teams")


def _require_role(team_id, min_role):
    try:
        return require_team_role(team_id, current_user.id, min_role)
    except PermissionError:
        abort(403)


def _team_property_or_404(team_id, property_id):
    db = get_db()
    row = db.execute(
        """
        SELECT id, team_id, address, slug, qr_code, created_at
        FROM properties
        WHERE id = %s AND team_id = %s
        LIMIT 1
        """,
        (property_id, team_id),
    ).fetchone()
    if not row:
        abort(404)
    return row


@teams_bp.route("")
@teams_bp.route("/")
@login_required
def index():
    teams = get_user_teams(current_user.id)
    return render_template("teams/index.html", teams=teams)


@teams_bp.route("/create", methods=["POST"])
@login_required
def create_team_route():
    name = request.form.get("name", "")
    try:
        team_id = create_team(current_user.id, name)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("teams.index"))
    except Exception as exc:
        current_app.logger.error("[Teams] team create failed for user_id=%s: %s", current_user.id, type(exc).__name__)
        flash("Could not create team.", "error")
        return redirect(url_for("teams.index"))

    flash("Team created.", "success")
    return redirect(url_for("teams.team_dashboard", team_id=team_id))


@teams_bp.route("/invite/<token>")
@login_required
def accept_invite_token(token):
    try:
        team_id = accept_invite(token, current_user.id)
    except PermissionError:
        abort(403)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("teams.index"))
    except Exception as exc:
        current_app.logger.error("[Teams] invite accept failed for user_id=%s: %s", current_user.id, type(exc).__name__)
        flash("Could not accept invite.", "error")
        return redirect(url_for("teams.index"))

    flash("Joined team successfully.", "success")
    return redirect(url_for("teams.team_dashboard", team_id=team_id))


@teams_bp.route("/<int:team_id>")
@login_required
def team_dashboard(team_id):
    membership = _require_role(team_id, "viewer")
    team = get_team(team_id)
    if not team:
        abort(404)

    db = get_db()
    properties = db.execute(
        """
        SELECT id, address, slug, created_at
        FROM properties
        WHERE team_id = %s
        ORDER BY created_at DESC
        """,
        (team_id,),
    ).fetchall()

    summary = db.execute(
        """
        SELECT
            COALESCE(SUM(CASE WHEN event_type = 'comment.created' THEN 1 ELSE 0 END), 0) AS comments_created,
            COALESCE(SUM(CASE WHEN event_type = 'file.uploaded' THEN 1 ELSE 0 END), 0) AS files_uploaded,
            COALESCE(SUM(CASE WHEN event_type = 'file.downloaded' THEN 1 ELSE 0 END), 0) AS files_downloaded
        FROM audit_events
        WHERE team_id = %s
          AND created_at >= NOW() - INTERVAL '30 days'
        """,
        (team_id,),
    ).fetchone()

    return render_template(
        "teams/team_dashboard.html",
        team=team,
        membership=membership,
        properties=properties,
        summary=summary,
    )


@teams_bp.route("/<int:team_id>/properties/<int:property_id>")
@login_required
def property_workspace(team_id, property_id):
    membership = _require_role(team_id, "viewer")
    property_row = _team_property_or_404(team_id, property_id)
    db = get_db()
    comments = db.execute(
        """
        SELECT
            pc.id,
            pc.body,
            pc.created_at,
            pc.author_user_id,
            COALESCE(u.full_name, u.email) AS author_name
        FROM property_comments pc
        JOIN users u ON u.id = pc.author_user_id
        WHERE pc.team_id = %s AND pc.property_id = %s
        ORDER BY pc.created_at DESC
        """,
        (team_id, property_id),
    ).fetchall()
    files = list_files(team_id, property_id)

    return render_template(
        "teams/property_workspace.html",
        team=get_team(team_id),
        membership=membership,
        property=property_row,
        comments=comments,
        files=files,
    )


@teams_bp.route("/<int:team_id>/properties/<int:property_id>/comments", methods=["POST"])
@login_required
def create_comment(team_id, property_id):
    _require_role(team_id, "member")
    _team_property_or_404(team_id, property_id)
    body = (request.form.get("body") or "").strip()
    if not body:
        flash("Comment cannot be empty.", "error")
        return redirect(url_for("teams.property_workspace", team_id=team_id, property_id=property_id))

    db = get_db()
    comment = db.execute(
        """
        INSERT INTO property_comments (team_id, property_id, author_user_id, body)
        VALUES (%s, %s, %s, %s)
        RETURNING id
        """,
        (team_id, property_id, current_user.id, body),
    ).fetchone()
    log_audit_event(
        db,
        team_id=team_id,
        actor_user_id=current_user.id,
        event_type="comment.created",
        object_type="property_comments",
        object_id=comment["id"],
        metadata={"property_id": property_id},
    )
    db.commit()

    flash("Comment added.", "success")
    return redirect(url_for("teams.property_workspace", team_id=team_id, property_id=property_id) + "#comments")


@teams_bp.route("/<int:team_id>/properties/<int:property_id>/files/upload", methods=["POST"])
@login_required
def upload_property_file(team_id, property_id):
    _require_role(team_id, "member")
    _team_property_or_404(team_id, property_id)
    upload = request.files.get("file")
    try:
        upload_file(team_id, property_id, current_user.id, upload, kind="upload")
    except ValueError as exc:
        flash(str(exc), "error")
    except Exception as exc:
        current_app.logger.error(
            "[Teams] file upload failed team_id=%s property_id=%s actor_user_id=%s error=%s",
            team_id,
            property_id,
            current_user.id,
            type(exc).__name__,
        )
        flash("Upload failed.", "error")
    else:
        flash("File uploaded.", "success")
    return redirect(url_for("teams.property_workspace", team_id=team_id, property_id=property_id) + "#files")


@teams_bp.route("/<int:team_id>/properties/<int:property_id>/files/export-leads", methods=["POST"])
@login_required
def export_property_leads(team_id, property_id):
    _require_role(team_id, "member")
    _team_property_or_404(team_id, property_id)
    try:
        generate_leads_export(team_id, property_id, current_user.id)
    except Exception as exc:
        current_app.logger.error(
            "[Teams] leads export failed team_id=%s property_id=%s actor_user_id=%s error=%s",
            team_id,
            property_id,
            current_user.id,
            type(exc).__name__,
        )
        flash("Could not generate leads export.", "error")
    else:
        flash("Leads export generated.", "success")
    return redirect(url_for("teams.property_workspace", team_id=team_id, property_id=property_id) + "#files")


@teams_bp.route("/<int:team_id>/files/<int:file_id>/download")
@login_required
def download_file(team_id, file_id):
    membership = _require_role(team_id, "viewer")
    try:
        return stream_download(team_id, file_id, current_user.id, membership["role"])
    except PermissionError:
        abort(403)
    except FileNotFoundError:
        abort(404)
    except Exception as exc:
        current_app.logger.error(
            "[Teams] file download failed team_id=%s file_id=%s actor_user_id=%s error=%s",
            team_id,
            file_id,
            current_user.id,
            type(exc).__name__,
        )
        abort(500)


@teams_bp.route("/<int:team_id>/files/<int:file_id>/delete", methods=["POST"])
@login_required
def delete_file_route(team_id, file_id):
    _require_role(team_id, "admin")
    try:
        row = delete_team_file(team_id, file_id, current_user.id)
        flash("File deleted.", "success")
        return redirect(
            url_for("teams.property_workspace", team_id=team_id, property_id=row["property_id"]) + "#files"
        )
    except FileNotFoundError:
        abort(404)
    except Exception as exc:
        current_app.logger.error(
            "[Teams] file delete failed team_id=%s file_id=%s actor_user_id=%s error=%s",
            team_id,
            file_id,
            current_user.id,
            type(exc).__name__,
        )
        flash("Could not delete file.", "error")
        return redirect(url_for("teams.team_dashboard", team_id=team_id))


@teams_bp.route("/<int:team_id>/settings", methods=["GET", "POST"])
@login_required
def team_settings(team_id):
    _require_role(team_id, "admin")
    team = get_team(team_id)
    if not team:
        abort(404)

    created_invite_url = None
    if request.method == "POST":
        action = (request.form.get("action") or "").strip()
        try:
            if action == "set_retention":
                days = request.form.get("retention_days")
                set_retention_days(team_id, current_user.id, days)
                flash("Retention updated.", "success")
            elif action == "invite_member":
                email = request.form.get("email")
                role = request.form.get("role", "viewer")
                token = invite_member(team_id, current_user.id, email, role)
                created_invite_url = url_for("teams.accept_invite_token", token=token, _external=True)
                flash("Invite created.", "success")
            else:
                flash("Unknown settings action.", "error")
        except PermissionError:
            abort(403)
        except ValueError as exc:
            flash(str(exc), "error")
        except Exception as exc:
            current_app.logger.error(
                "[Teams] settings update failed team_id=%s actor_user_id=%s error=%s",
                team_id,
                current_user.id,
                type(exc).__name__,
            )
            flash("Could not update team settings.", "error")

    members = get_team_members(team_id)
    invites = get_team_invites(team_id)
    return render_template(
        "teams/settings.html",
        team=team,
        members=members,
        invites=invites,
        created_invite_url=created_invite_url,
    )
