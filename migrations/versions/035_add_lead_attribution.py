"""add_lead_attribution

Add sign_asset_id and source columns to leads table for SmartSign attribution.

Revision ID: 035_add_lead_attribution
Revises: 034_add_scheduling_and_virtual_tour_urls
Create Date: 2026-01-30
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '035_add_lead_attribution'
down_revision = '034_scheduling_tour_urls'
branch_labels = None
depends_on = None


def upgrade():
    # Add sign_asset_id column to leads table
    op.execute("""
        ALTER TABLE leads 
        ADD COLUMN IF NOT EXISTS sign_asset_id INTEGER 
        REFERENCES sign_assets(id) ON DELETE SET NULL
    """)
    
    # Add source column with default 'direct'
    op.execute("""
        ALTER TABLE leads 
        ADD COLUMN IF NOT EXISTS source VARCHAR(20) NOT NULL DEFAULT 'direct'
    """)
    
    # Create index for efficient per-asset lead queries
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_leads_sign_asset_id 
        ON leads(sign_asset_id) 
        WHERE sign_asset_id IS NOT NULL
    """)


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_leads_sign_asset_id")
    op.execute("ALTER TABLE leads DROP COLUMN IF EXISTS source")
    op.execute("ALTER TABLE leads DROP COLUMN IF EXISTS sign_asset_id")
