"""add v2 agent fields

Revision ID: 036
Revises: 035
Create Date: 2026-02-04 17:15:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import text

# revision identifiers, used by Alembic.
revision = '036'
down_revision = '035_add_lead_attribution'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Add new columns to sign_assets
    # Use batch_alter_table if we were on sqlite, but this is postgres so direct add_column is fine
    # However, safe check if column exists is good practice
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c['name'] for c in inspector.get_columns('sign_assets')]
    
    if 'agent_name' not in columns:
        op.add_column('sign_assets', sa.Column('agent_name', sa.Text(), nullable=True))
        
    if 'agent_phone' not in columns:
        op.add_column('sign_assets', sa.Column('agent_phone', sa.Text(), nullable=True))
        
    if 'state' not in columns:
        op.add_column('sign_assets', sa.Column('state', sa.String(2), nullable=True))
        
    if 'license_number' not in columns:
        op.add_column('sign_assets', sa.Column('license_number', sa.Text(), nullable=True))
        
    if 'show_license_option' not in columns:
        # Add as text with default 'auto'
        op.add_column('sign_assets', sa.Column('show_license_option', sa.Text(), server_default='auto', nullable=False))
        
    if 'license_label_override' not in columns:
        op.add_column('sign_assets', sa.Column('license_label_override', sa.Text(), nullable=True))

    # 2. Backfill existing rows
    # brand_name -> agent_name if agent_name is null
    op.execute(text("UPDATE sign_assets SET agent_name = brand_name WHERE agent_name IS NULL AND brand_name IS NOT NULL"))
    
    # phone -> agent_phone if agent_phone is null
    op.execute(text("UPDATE sign_assets SET agent_phone = phone WHERE agent_phone IS NULL AND phone IS NOT NULL"))
    
    # Ensure show_license_option is 'auto' (handled by server_default, but good to be explicit for existing rows if default didn't apply retrospectively in some DBs without defaults logic, though postgres handles it)
    # The server_default handles new rows and backfills existing rows with the default value at creation time if the column is NOT NULL.
    # Since we added it as NOT NULL with DEFAULT, Postgres backfills 'auto' automatically.

    print("[Migration 036] Added V2 fields to sign_assets and backfilled data.")


def downgrade():
    op.drop_column('sign_assets', 'license_label_override')
    op.drop_column('sign_assets', 'show_license_option')
    op.drop_column('sign_assets', 'license_number')
    op.drop_column('sign_assets', 'state')
    op.drop_column('sign_assets', 'agent_phone')
    op.drop_column('sign_assets', 'agent_name')
