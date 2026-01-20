"""add_smart_signs_tables

Revision ID: 010
Revises: 009
Create Date: 2026-01-19 19:40:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '010_smart_signs_mvp'
down_revision = '009_add_agent_snapshots'
branch_labels = None
depends_on = None


def upgrade():
    # Helper to check if table exists
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    # 1. Create sign_assets table
    if 'sign_assets' not in existing_tables:
        op.create_table('sign_assets',
            sa.Column('id', sa.BigInteger(), sa.Identity(), primary_key=True),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('code', sa.Text(), nullable=False),
            sa.Column('label', sa.Text(), nullable=True),
            sa.Column('active_property_id', sa.Integer(), nullable=True),
            sa.Column('activated_at', sa.DateTime(), nullable=True),
            sa.Column('activation_order_id', sa.Integer(), nullable=True),
            sa.Column('is_frozen', sa.Boolean(), server_default='false', nullable=False),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['active_property_id'], ['properties.id'], ondelete='SET NULL'),
            sa.ForeignKeyConstraint(['activation_order_id'], ['orders.id'], ),
            sa.UniqueConstraint('code')
        )
        op.create_index(op.f('ix_sign_assets_code'), 'sign_assets', ['code'], unique=True)
        op.create_index(op.f('ix_sign_assets_user_id'), 'sign_assets', ['user_id'], unique=False)
    else:
        print("Table 'sign_assets' already exists, skipping creation.")

    # 2. Create sign_asset_history table
    if 'sign_asset_history' not in existing_tables:
        op.create_table('sign_asset_history',
            sa.Column('id', sa.BigInteger(), sa.Identity(), primary_key=True),
            sa.Column('sign_asset_id', sa.BigInteger(), nullable=False),
            sa.Column('old_property_id', sa.Integer(), nullable=True),
            sa.Column('new_property_id', sa.Integer(), nullable=True),
            sa.Column('changed_by_user_id', sa.Integer(), nullable=True),
            sa.Column('changed_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
            sa.ForeignKeyConstraint(['sign_asset_id'], ['sign_assets.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['old_property_id'], ['properties.id'], ),
            sa.ForeignKeyConstraint(['new_property_id'], ['properties.id'], ),
            sa.ForeignKeyConstraint(['changed_by_user_id'], ['users.id'], )
        )
        op.create_index(op.f('ix_sign_asset_history_sign_asset_id'), 'sign_asset_history', ['sign_asset_id'], unique=False)
        op.create_index(op.f('ix_sign_asset_history_changed_at'), 'sign_asset_history', ['changed_at'], unique=False)
    else:
        print("Table 'sign_asset_history' already exists, skipping creation.")

    # 3. Update qr_scans table
    # Check if column exists first to be safe (idempotency)
    columns = [c['name'] for c in inspector.get_columns('qr_scans')]
    if 'sign_asset_id' not in columns:
        op.add_column('qr_scans', sa.Column('sign_asset_id', sa.BigInteger(), nullable=True))
        op.create_foreign_key('fk_qr_scans_sign_asset_id', 'qr_scans', 'sign_assets', ['sign_asset_id'], ['id'])
        op.create_index(op.f('ix_qr_scans_sign_asset_id'), 'qr_scans', ['sign_asset_id'], unique=False)
    else:
        print("Column 'sign_asset_id' already exists in 'qr_scans', skipping addition.")


def downgrade():
    # Drop columns and tables in reverse order
    op.drop_index(op.f('ix_qr_scans_sign_asset_id'), table_name='qr_scans')
    op.drop_constraint('fk_qr_scans_sign_asset_id', 'qr_scans', type_='foreignkey')
    op.drop_column('qr_scans', 'sign_asset_id')
    
    op.drop_table('sign_asset_history')
    op.drop_table('sign_assets')
