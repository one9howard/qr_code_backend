"""Create lead_notifications audit table

Revision ID: 004
Revises: 003
Create Date: 2026-01-12 15:30:00.000000

Note: This migration creates the lead_notifications table and related indexes.
It includes an idempotency check to avoid errors if the table already exists.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade():
    # Idempotency check
    conn = op.get_bind()
    inspector = inspect(conn)
    if 'lead_notifications' in inspector.get_table_names():
        return

    # Create lead_notifications table with correct schema
    op.create_table('lead_notifications',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column('lead_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.Text(), nullable=False),
        sa.Column('channel', sa.Text(), server_default='email', nullable=True),
        sa.Column('sent_at', sa.DateTime(), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['lead_id'], ['leads.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes
    op.create_index(op.f('ix_lead_notifications_lead_id'), 'lead_notifications', ['lead_id'], unique=False)
    op.create_index(op.f('ix_lead_notifications_status'), 'lead_notifications', ['status'], unique=False)
    op.create_index(op.f('ix_lead_notifications_created_at'), 'lead_notifications', ['created_at'], unique=False)


def downgrade():
    conn = op.get_bind()
    inspector = inspect(conn)
    if 'lead_notifications' in inspector.get_table_names():
        op.drop_index(op.f('ix_lead_notifications_created_at'), table_name='lead_notifications')
        op.drop_index(op.f('ix_lead_notifications_status'), table_name='lead_notifications')
        op.drop_index(op.f('ix_lead_notifications_lead_id'), table_name='lead_notifications')
        op.drop_table('lead_notifications')
