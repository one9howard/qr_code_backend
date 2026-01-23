"""add_app_events

Revision ID: 019
Revises: 018
Create Date: 2026-01-22 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '019'
down_revision = '018'
branch_labels = None
depends_on = None


def upgrade():
    # Create app_events table
    op.create_table('app_events',
        sa.Column('id', sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column('occurred_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('event_type', sa.Text(), nullable=False),
        sa.Column('source', sa.Text(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('property_id', sa.Integer(), nullable=True),
        sa.Column('sign_asset_id', sa.Integer(), nullable=True),
        sa.Column('order_id', sa.Integer(), nullable=True),
        sa.Column('qr_code', sa.Text(), nullable=True),
        sa.Column('session_id', sa.Text(), nullable=True),
        sa.Column('request_id', sa.Text(), nullable=True),
        sa.Column('ip_hash', sa.Text(), nullable=True),
        sa.Column('ua_hash', sa.Text(), nullable=True),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False)
    )

    # Indexes
    op.create_index('idx_app_events_type_time', 'app_events', ['event_type', sa.text('occurred_at DESC')])
    op.create_index('idx_app_events_property_time', 'app_events', ['property_id', sa.text('occurred_at DESC')])
    op.create_index('idx_app_events_user_time', 'app_events', ['user_id', sa.text('occurred_at DESC')])
    op.create_index('idx_app_events_qr_time', 'app_events', ['qr_code', sa.text('occurred_at DESC')])


def downgrade():
    op.drop_index('idx_app_events_qr_time', table_name='app_events')
    op.drop_index('idx_app_events_user_time', table_name='app_events')
    op.drop_index('idx_app_events_property_time', table_name='app_events')
    op.drop_index('idx_app_events_type_time', table_name='app_events')
    op.drop_table('app_events')
