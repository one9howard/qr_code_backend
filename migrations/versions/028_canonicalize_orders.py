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
