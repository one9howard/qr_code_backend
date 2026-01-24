"""
Migration 023: Sign Assets Activation Requires Order

Option B enforcement: activated_at can ONLY be set when activation_order_id is also set.

1. Backfill bad data (activated without order)
2. Add CHECK constraint enforcing the invariant
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = '023'
down_revision = '022'
branch_labels = None
depends_on = None

# Paid order statuses that qualify for activation
PAID_STATUSES = ('paid', 'completed', 'submitted_to_printer', 'shipped', 'delivered')


def upgrade():
    """
    Backfill bad rows and add CHECK constraint.
    """
    conn = op.get_bind()
    
    # 1. First, add activation_order_id column if it doesn't exist
    inspector = sa.inspect(conn)
    columns = [c['name'] for c in inspector.get_columns('sign_assets')]
    if 'activation_order_id' not in columns:
        op.add_column('sign_assets', sa.Column('activation_order_id', sa.BigInteger(), nullable=True))
        op.create_foreign_key(
            'fk_sign_assets_activation_order',
            'sign_assets', 'orders',
            ['activation_order_id'], ['id']
        )
        print("[Migration 023] Added activation_order_id column")

    # 1b. Fix orders table: property_id must be nullable for SmartSign orders
    # Check if nullable first? alter_column is usually safe
    op.alter_column('orders', 'property_id', nullable=True)
    print("[Migration 023] Made orders.property_id nullable")
    
    # 2. Backfill: find assets with activated_at but no activation_order_id
    bad_assets = conn.execute(text("""
        SELECT id FROM sign_assets 
        WHERE activated_at IS NOT NULL 
          AND activation_order_id IS NULL
    """)).fetchall()
    
    print(f"[Migration 023] Found {len(bad_assets)} assets activated without order")
    
    for (asset_id,) in bad_assets:
        # Try to find a paid order for this asset
        # Use ANY with array for safe Postgres binding (avoids fragile tuple IN clause)
        order = conn.execute(text("""
            SELECT id FROM orders 
            WHERE sign_asset_id = :asset_id 
              AND order_type = 'smart_sign'
              AND status = ANY(:statuses)
            ORDER BY id LIMIT 1
        """), {"asset_id": asset_id, "statuses": list(PAID_STATUSES)}).fetchone()
        
        if order:
            # Link to the order
            conn.execute(text("""
                UPDATE sign_assets SET activation_order_id = :order_id WHERE id = :asset_id
            """), {"order_id": order[0], "asset_id": asset_id})
            print(f"[Migration 023] Asset {asset_id} linked to order {order[0]}")
        else:
            # Deactivate - no valid order
            conn.execute(text("""
                UPDATE sign_assets SET activated_at = NULL WHERE id = :asset_id
            """), {"asset_id": asset_id})
            print(f"[Migration 023] Asset {asset_id} deactivated (no paid order found)")
    
    # 3. Add CHECK constraint
    # (activated_at IS NULL) OR (activation_order_id IS NOT NULL)
    op.execute("""
        ALTER TABLE sign_assets 
        ADD CONSTRAINT chk_activation_requires_order 
        CHECK (activated_at IS NULL OR activation_order_id IS NOT NULL)
    """)
    print("[Migration 023] Added CHECK constraint: chk_activation_requires_order")


def downgrade():
    """
    Remove the CHECK constraint. Data remains intact.
    """
    op.execute("ALTER TABLE sign_assets DROP CONSTRAINT IF EXISTS chk_activation_requires_order")
    print("[Migration 023] Removed CHECK constraint")
    
    # Revert property_id to NOT NULL
    # NOTE: This might fail if rows have NULL property_id.
    # We attempt it, but if it fails, user must purge data.
    try:
        op.alter_column('orders', 'property_id', nullable=False)
        print("[Migration 023] Reverted orders.property_id to NOT NULL")
    except Exception as e:
        print(f"[Migration 023] WARNING: Could not revert property_id to NOT NULL: {e}")

    # Note: We don't drop the activation_order_id column or FK - it's harmless to keep
