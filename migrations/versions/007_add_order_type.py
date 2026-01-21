"""Add order type and transaction fields

Revision ID: 007_add_order_type
Revises: 006_lead_management
Create Date: 2026-01-16 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '007_add_order_type'
down_revision = '006_lead_management'
branch_labels = None
depends_on = None

def upgrade():
    # Helper to check columns exists before adding (idempotent)
    # But for Alembic with Postgres we can just use add_column with server_default if needed
    
    # 1. order_type
    op.add_column('orders', sa.Column('order_type', sa.String(length=50), server_default='sign', nullable=False))
    
    # 2. Transaction details
    op.add_column('orders', sa.Column('amount_total_cents', sa.Integer(), nullable=True))
    op.add_column('orders', sa.Column('currency', sa.String(length=10), nullable=True))
    
    # 3. Index on order_type for filtering
    op.create_index(op.f('ix_orders_order_type'), 'orders', ['order_type'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_orders_order_type'), table_name='orders')
    op.drop_column('orders', 'currency')
    op.drop_column('orders', 'amount_total_cents')
    op.drop_column('orders', 'order_type')
