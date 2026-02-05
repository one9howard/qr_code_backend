"""
Rename listing_sign to yard_sign in orders

Revision ID: 038_rename_listing_to_yard_sign
Revises: 037_add_agent_license_fields
Create Date: 2026-02-05 16:00:00

"""
import sqlalchemy as sa
from alembic import op

revision = '038'
down_revision = '037'
branch_labels = None
depends_on = None

def upgrade():
    # Update print_product values
    op.execute("""
        UPDATE orders 
        SET print_product = REPLACE(print_product, 'listing_sign', 'yard_sign')
        WHERE print_product LIKE 'listing_sign%'
    """)
    
    # Update order_type
    # Note: 'listing_sign' was sometimes used as order_type/canonical type
    op.execute("""
        UPDATE orders 
        SET order_type = 'yard_sign'
        WHERE order_type = 'listing_sign'
    """)

def downgrade():
    op.execute("""
        UPDATE orders 
        SET print_product = REPLACE(print_product, 'yard_sign', 'listing_sign')
        WHERE print_product LIKE 'yard_sign%'
    """)
    
    op.execute("""
        UPDATE orders 
        SET order_type = 'listing_sign'
        WHERE order_type = 'yard_sign'
    """)
