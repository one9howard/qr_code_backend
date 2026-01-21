"""Add print SKU specification columns to orders

Revision ID: 017_print_sku_spec
Revises: 016_events_mvp
Create Date: 2026-01-21

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '017'
down_revision = '016'
branch_labels = None
depends_on = None


def upgrade():
    # Add print SKU columns to orders table
    op.execute("""
        ALTER TABLE orders 
        ADD COLUMN IF NOT EXISTS print_product TEXT,
        ADD COLUMN IF NOT EXISTS material TEXT,
        ADD COLUMN IF NOT EXISTS sides TEXT,
        ADD COLUMN IF NOT EXISTS layout_id TEXT,
        ADD COLUMN IF NOT EXISTS design_payload JSONB,
        ADD COLUMN IF NOT EXISTS design_version INTEGER NOT NULL DEFAULT 1
    """)


def downgrade():
    op.execute("""
        ALTER TABLE orders 
        DROP COLUMN IF EXISTS design_version,
        DROP COLUMN IF EXISTS design_payload,
        DROP COLUMN IF EXISTS layout_id,
        DROP COLUMN IF EXISTS sides,
        DROP COLUMN IF EXISTS material,
        DROP COLUMN IF EXISTS print_product
    """)
