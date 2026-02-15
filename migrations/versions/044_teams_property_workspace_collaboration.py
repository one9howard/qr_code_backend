"""teams + property workspace collaboration

Revision ID: 044
Revises: 043
Create Date: 2026-02-15 10:40:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "044"
down_revision = "043"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "teams",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("retention_days", sa.Integer(), nullable=False, server_default=sa.text("60")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], name="fk_teams_owner_user_id"),
    )

    op.create_table(
        "team_members",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'active'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE", name="fk_team_members_team_id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE", name="fk_team_members_user_id"),
        sa.UniqueConstraint("team_id", "user_id", name="uq_team_members_team_user"),
        sa.CheckConstraint("role IN ('admin','member','viewer')", name="ck_team_members_role"),
        sa.CheckConstraint("status IN ('active','invited')", name="ck_team_members_status"),
    )
    op.create_index("idx_team_members_team_role", "team_members", ["team_id", "role"])
    op.create_index("idx_team_members_user_id", "team_members", ["user_id"])

    op.create_table(
        "team_invites",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False, server_default=sa.text("'viewer'")),
        sa.Column("token", sa.String(length=255), nullable=False),
        sa.Column("invited_by_user_id", sa.Integer(), nullable=False),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now() + interval '7 days'"),
        ),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE", name="fk_team_invites_team_id"),
        sa.ForeignKeyConstraint(
            ["invited_by_user_id"], ["users.id"], ondelete="CASCADE", name="fk_team_invites_invited_by_user_id"
        ),
        sa.CheckConstraint("role IN ('viewer','member')", name="ck_team_invites_role"),
        sa.UniqueConstraint("token", name="uq_team_invites_token"),
    )
    op.execute("CREATE INDEX idx_team_invites_team_email_ci ON team_invites (team_id, lower(email))")

    op.add_column("properties", sa.Column("team_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_properties_team_id", "properties", "teams", ["team_id"], ["id"], ondelete="SET NULL")
    op.create_index("idx_properties_team_id", "properties", ["team_id"])

    op.create_table(
        "property_comments",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("property_id", sa.Integer(), nullable=False),
        sa.Column("author_user_id", sa.Integer(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE", name="fk_property_comments_team_id"),
        sa.ForeignKeyConstraint(
            ["property_id"], ["properties.id"], ondelete="CASCADE", name="fk_property_comments_property_id"
        ),
        sa.ForeignKeyConstraint(
            ["author_user_id"], ["users.id"], ondelete="CASCADE", name="fk_property_comments_author_user_id"
        ),
    )
    op.create_index("idx_property_comments_property_created", "property_comments", ["property_id", "created_at"])

    op.create_table(
        "property_files",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("property_id", sa.Integer(), nullable=False),
        sa.Column("uploader_user_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("original_filename", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE", name="fk_property_files_team_id"),
        sa.ForeignKeyConstraint(
            ["property_id"], ["properties.id"], ondelete="CASCADE", name="fk_property_files_property_id"
        ),
        sa.ForeignKeyConstraint(
            ["uploader_user_id"], ["users.id"], ondelete="CASCADE", name="fk_property_files_uploader_user_id"
        ),
        sa.CheckConstraint("kind IN ('upload','export')", name="ck_property_files_kind"),
    )
    op.create_index("idx_property_files_team_property_created", "property_files", ["team_id", "property_id", "created_at"])
    op.create_index(
        "idx_property_files_expires_active",
        "property_files",
        ["expires_at"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("object_type", sa.String(length=50), nullable=True),
        sa.Column("object_id", sa.Integer(), nullable=True),
        sa.Column("ip", sa.Text(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE", name="fk_audit_events_team_id"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL", name="fk_audit_events_actor_user_id"),
    )
    op.create_index("idx_audit_events_team_created", "audit_events", ["team_id", "created_at"])
    op.create_index("idx_audit_events_event_created", "audit_events", ["event_type", "created_at"])


def downgrade():
    op.drop_index("idx_audit_events_event_created", table_name="audit_events")
    op.drop_index("idx_audit_events_team_created", table_name="audit_events")
    op.drop_table("audit_events")

    op.drop_index("idx_property_files_expires_active", table_name="property_files")
    op.drop_index("idx_property_files_team_property_created", table_name="property_files")
    op.drop_table("property_files")

    op.drop_index("idx_property_comments_property_created", table_name="property_comments")
    op.drop_table("property_comments")

    op.drop_index("idx_properties_team_id", table_name="properties")
    op.drop_constraint("fk_properties_team_id", "properties", type_="foreignkey")
    op.drop_column("properties", "team_id")

    op.execute("DROP INDEX IF EXISTS idx_team_invites_team_email_ci")
    op.drop_table("team_invites")

    op.drop_index("idx_team_members_user_id", table_name="team_members")
    op.drop_index("idx_team_members_team_role", table_name="team_members")
    op.drop_table("team_members")

    op.drop_table("teams")
