"""smart_signs_printing

Revision ID: 011
Revises: 010_smart_signs_mvp
Create Date: 2026-01-20 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '011'
down_revision = '010_smart_signs_mvp'
branch_labels = None
depends_on = None



def upgrade():
    # --- sign_assets additions ---
    # Unconditional additions
    op.add_column('sign_assets', sa.Column('brand_name', sa.Text(), nullable=True))
    op.add_column('sign_assets', sa.Column('phone', sa.Text(), nullable=True))
    op.add_column('sign_assets', sa.Column('email', sa.Text(), nullable=True))
        
    # presets
    op.add_column('sign_assets', sa.Column('cta_key', sa.Text(), server_default='scan_for_details', nullable=False))
    op.add_column('sign_assets', sa.Column('background_style', sa.Text(), server_default='solid_blue', nullable=False))
    
    # images
    op.add_column('sign_assets', sa.Column('logo_key', sa.Text(), nullable=True))
    op.add_column('sign_assets', sa.Column('headshot_key', sa.Text(), nullable=True))
    op.add_column('sign_assets', sa.Column('include_logo', sa.Boolean(), server_default='true', nullable=False))
    op.add_column('sign_assets', sa.Column('include_headshot', sa.Boolean(), server_default='false', nullable=False))

    # --- orders additions ---
    op.add_column('orders', sa.Column('sign_asset_id', sa.BigInteger(), nullable=True))
    
    # Safe constraint creation
    op.create_foreign_key('fk_orders_sign_asset_id', 'orders', 'sign_assets', ['sign_asset_id'], ['id'], ondelete='SET NULL')
    op.create_index(op.f('ix_orders_sign_asset_id'), 'orders', ['sign_asset_id'], unique=False)


def downgrade():
    # Only drop if they exist - simplified for downgrade
    # but strictly speaking, upgrade is the critical path
    
    op.drop_index(op.f('ix_orders_sign_asset_id'), table_name='orders')
    op.drop_constraint('fk_orders_sign_asset_id', 'orders', type_='foreignkey')
    op.drop_column('orders', 'sign_asset_id')

    op.drop_column('sign_assets', 'include_headshot')
    op.drop_column('sign_assets', 'include_logo')
    op.drop_column('sign_assets', 'headshot_key')
    op.drop_column('sign_assets', 'logo_key')
    op.drop_column('sign_assets', 'background_style')
    op.drop_column('sign_assets', 'cta_key')
    op.drop_column('sign_assets', 'email')
    op.drop_column('sign_assets', 'phone')
    op.drop_column('sign_assets', 'brand_name')
