"""add_updated_at_to_orders

Revision ID: 022
Revises: 021
Create Date: 2026-01-23

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '022'
down_revision = '021'
branch_labels = None
depends_on = None

def upgrade():
    # Add updated_at column to orders
    op.add_column('orders', sa.Column('updated_at', sa.DateTime(), nullable=True))
    
    # Optional: set default to NOW for existing rows
    op.execute("UPDATE orders SET updated_at = NOW() WHERE updated_at IS NULL")

def downgrade():
    op.drop_column('orders', 'updated_at')
