"""add_custom_url_to_properties

Revision ID: 041
Revises: 040_add_slug_unique_constraint
Create Date: 2026-02-08 12:55:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '041'
down_revision = '040'
branch_labels = None
depends_on = None


def upgrade():
    # Helper to check if column exists (idempotency)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c['name'] for c in inspector.get_columns('properties')]
    
    if 'custom_url' not in columns:
        op.add_column('properties', sa.Column('custom_url', sa.String(), nullable=True))


def downgrade():
    op.drop_column('properties', 'custom_url')
