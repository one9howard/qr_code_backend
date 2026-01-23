"""Agent Actions Table

Revision ID: 020
Revises: 019
Create Date: 2026-01-22 20:45:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '020'
down_revision = '019'
branch_labels = None
depends_on = None

def upgrade():
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # --- Create agent_actions ---
    op.create_table('agent_actions',
        sa.Column('id', sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column('action_uuid', postgresql.UUID(as_uuid=True), server_default=sa.text('uuid_generate_v4()'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('created_by_type', sa.Text(), nullable=False),
        sa.Column('created_by_id', sa.Integer(), nullable=True),
        
        sa.Column('property_id', sa.Integer(), nullable=True),
        sa.Column('lead_id', sa.Integer(), nullable=True),
        sa.Column('sign_asset_id', sa.Integer(), nullable=True),
        sa.Column('order_id', sa.Integer(), nullable=True),
        
        sa.Column('action_type', sa.Text(), nullable=False),
        sa.Column('status', sa.Text(), nullable=False),
        
        sa.Column('proposal', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
        sa.Column('execution', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('policy_snapshot', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
        sa.Column('input_event_refs', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        
        sa.Column('requires_approval', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('approved_by_user_id', sa.Integer(), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rejected_by_user_id', sa.Integer(), nullable=True),
        sa.Column('rejected_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rejection_reason', sa.Text(), nullable=True),
        
        sa.Column('execute_after', sa.DateTime(timezone=True), nullable=True),
        sa.Column('executed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_code', sa.Text(), nullable=True),
        sa.Column('error_detail', sa.Text(), nullable=True)
    )
    
    op.create_index('idx_agent_actions_user_time', 'agent_actions', ['user_id', sa.text('created_at DESC')])
    op.create_index('idx_agent_actions_status_execute_after', 'agent_actions', ['status', 'execute_after'])
    op.create_index('idx_agent_actions_lead_time', 'agent_actions', ['lead_id', sa.text('created_at DESC')])
    op.create_index('idx_agent_actions_property_time', 'agent_actions', ['property_id', sa.text('created_at DESC')])

def downgrade():
    op.drop_table('agent_actions')
