"""add v2 schema fields

Revision ID: 025
Revises: 024
Create Date: 2026-01-25 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '025'
down_revision = '024'
branch_labels = None
depends_on = None


def upgrade():
    # 1. agents.logo_filename
    # Inspect to see if column exists before adding (Idempotency)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns_agents = [c['name'] for c in inspector.get_columns('agents')]
    
    if 'logo_filename' not in columns_agents:
        op.add_column('agents', sa.Column('logo_filename', sa.Text(), nullable=True))

    # 2. orders.preview_key
    columns_orders = [c['name'] for c in inspector.get_columns('orders')]
    if 'preview_key' not in columns_orders:
        op.add_column('orders', sa.Column('preview_key', sa.Text(), nullable=True))
        
    # 3. orders.guest_email (Also covered in migrate_v2 previously, ensuring here)
    if 'guest_email' not in columns_orders:
         op.add_column('orders', sa.Column('guest_email', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('orders', 'guest_email')
    op.drop_column('orders', 'preview_key')
    op.drop_column('agents', 'logo_filename')
