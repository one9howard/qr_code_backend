"""fix_order_type_after_038

Revision ID: 042
Revises: 041
Create Date: 2026-02-09 10:50:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '042'
down_revision = '041'
branch_labels = None
depends_on = None


def upgrade():
    # Canonicalize order_type: 'yard_sign' or 'listing_sign' -> 'sign'
    # 'sign' is the correct canonical value for yard signs in the backend services.
    # We DO NOT touch print_product (which should be 'yard_sign_...')
    op.execute("""
        UPDATE orders 
        SET order_type = 'sign' 
        WHERE order_type IN ('yard_sign', 'listing_sign')
    """)


def downgrade():
    # Intentionally no-op. 
    # We do not want to revert data to non-canonical 'yard_sign' or 'listing_sign' 
    # as that breaks fulfillment logic as identified in the fix.
    pass
