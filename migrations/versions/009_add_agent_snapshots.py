"""Add agent_snapshots table

Revision ID: 009_add_agent_snapshots
Revises: 008_add_email_verification
Create Date: 2026-01-18 15:15:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '009_add_agent_snapshots'
down_revision = '008_add_email_verification'
branch_labels = None
depends_on = None


def upgrade():
    # Helper to check if table exists (idempotent-ish)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    if 'agent_snapshots' not in tables:
        op.create_table(
            'agent_snapshots',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('order_id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(), nullable=False),
            sa.Column('brokerage', sa.String(), nullable=True),
            sa.Column('email', sa.String(), nullable=False),
            sa.Column('phone', sa.String(), nullable=True),
            sa.Column('photo_filename', sa.String(), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['order_id'], ['orders.id'], )
        )


def downgrade():
    op.drop_table('agent_snapshots')
