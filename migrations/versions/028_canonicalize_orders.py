"""canonicalize_orders

Revision ID: 028
Revises: 027
Create Date: 2026-01-25 17:00:00

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '028'
down_revision = '027'
branch_labels = None
depends_on = None

def upgrade():
    # 0. Add missing columns safely
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_columns = [c['name'] for c in inspector.get_columns('orders')]

    if 'print_product' not in existing_columns:
        op.add_column('orders', sa.Column('print_product', sa.String(), nullable=True))
    if 'material' not in existing_columns:
        op.add_column('orders', sa.Column('material', sa.String(), nullable=True))
    if 'sides' not in existing_columns:
        op.add_column('orders', sa.Column('sides', sa.String(), nullable=True))
    
    # 1. Update existing 'listing_sign' orders to 'sign'
    # and map them to a default print_product if missing
    op.execute("""
        UPDATE orders 
        SET order_type = 'sign',
            print_product = COALESCE(print_product, 'listing_sign_coroplast_18x24'),
            material = COALESCE(material, 'coroplast'),
            sides = COALESCE(sides, 'single'),
            updated_at = NOW()
        WHERE order_type = 'listing_sign'
    """)
    
    # 2. Add comment/constraint? (Optional, just cleanup for now)

def downgrade():
    # Reverting is ambiguous because 'sign' is a broad bucket.
    # We can try to revert based on print_product but it's lossy.
    op.execute("""
        UPDATE orders 
        SET order_type = 'listing_sign'
        WHERE order_type = 'sign' 
          AND print_product LIKE 'listing_sign_%'
    """)
