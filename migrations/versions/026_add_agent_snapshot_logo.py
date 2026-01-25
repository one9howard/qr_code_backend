"""add agent_snapshot logo

Revision ID: 026
Revises: 025
Create Date: 2026-01-25 12:15:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '026'
down_revision = '025'
branch_labels = None
depends_on = None


def upgrade():
    # Check if column exists to be idempotent
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c['name'] for c in inspector.get_columns('agent_snapshots')]
    
    if 'logo_filename' not in columns:
        op.add_column('agent_snapshots', sa.Column('logo_filename', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('agent_snapshots', 'logo_filename')
