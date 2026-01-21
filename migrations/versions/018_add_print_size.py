"""Add print_size column to orders

Revision ID: 018_add_print_size
Revises: 017_print_sku_spec
Create Date: 2026-01-21

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '018'
down_revision = '017'
branch_labels = None
depends_on = None


def upgrade():
    # Add print_size column to orders table
    op.execute("""
        ALTER TABLE orders 
        ADD COLUMN IF NOT EXISTS print_size TEXT
    """)


def downgrade():
    op.execute("""
        ALTER TABLE orders 
        DROP COLUMN IF EXISTS print_size
    """)
