"""enforce unique agent email (case-insensitive)

Revision ID: 043
Revises: 042
Create Date: 2026-02-15 14:10:00.000000
"""

from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision = "043"
down_revision = "042"
branch_labels = None
depends_on = None


def _build_duplicate_error_message(dupes):
    sample = []
    for row in dupes:
        sample.append(f"email={row['email_key']} count={row['cnt']} ids={row['ids']}")
    sample_text = "\n".join(sample)
    return (
        "Cannot enforce case-insensitive unique agent email because duplicate rows already exist.\n"
        "Resolve duplicates manually, then rerun migration.\n\n"
        f"Sample duplicates:\n{sample_text}\n\n"
        "Admin remediation SQL (review before executing):\n"
        "WITH ranked AS (\n"
        "  SELECT id,\n"
        "         lower(email) AS email_key,\n"
        "         FIRST_VALUE(id) OVER (\n"
        "           PARTITION BY lower(email)\n"
        "           ORDER BY (user_id IS NULL), id\n"
        "         ) AS keep_id,\n"
        "         ROW_NUMBER() OVER (\n"
        "           PARTITION BY lower(email)\n"
        "           ORDER BY (user_id IS NULL), id\n"
        "         ) AS rn\n"
        "  FROM agents\n"
        "), dupes AS (\n"
        "  SELECT id, keep_id FROM ranked WHERE rn > 1\n"
        ")\n"
        "UPDATE properties p SET agent_id = d.keep_id FROM dupes d WHERE p.agent_id = d.id;\n"
        "UPDATE leads l SET agent_id = d.keep_id FROM dupes d WHERE l.agent_id = d.id;\n"
        "DELETE FROM agents a USING dupes d WHERE a.id = d.id;\n"
    )


def upgrade():
    conn = op.get_bind()

    # Canonicalize for deterministic matching.
    op.execute("UPDATE agents SET email = lower(trim(email)) WHERE email <> lower(trim(email))")

    dupes = conn.execute(
        text(
            """
            SELECT
                lower(email) AS email_key,
                COUNT(*) AS cnt,
                array_agg(id ORDER BY (user_id IS NULL), id) AS ids
            FROM agents
            GROUP BY lower(email)
            HAVING COUNT(*) > 1
            ORDER BY cnt DESC, email_key ASC
            LIMIT 10
            """
        )
    ).mappings().all()

    if dupes:
        raise RuntimeError(_build_duplicate_error_message(dupes))

    op.execute("CREATE UNIQUE INDEX uq_agents_email_ci ON agents (lower(email))")


def downgrade():
    op.execute("DROP INDEX IF EXISTS uq_agents_email_ci")

