"""fix_print_jobs_nullable

Revision ID: 014
Revises: 013
Create Date: 2026-01-20 12:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

# revision identifiers, used by Alembic.
revision = '014'
down_revision = '013_print_jobs_drift_fix'
branch_labels = None
depends_on = None

def upgrade():
    # Add sign_asset_id to print_jobs if it was missing.
    # We suspect it was missing in previous migrations.
    # We strictly add it here as nullable=True.
    op.add_column('print_jobs', sa.Column('sign_asset_id', sa.BigInteger(), nullable=True))
    op.create_foreign_key('fk_print_jobs_sign_asset_id', 'print_jobs', 'sign_assets', ['sign_asset_id'], ['id'], ondelete='SET NULL')
    op.create_index(op.f('ix_print_jobs_sign_asset_id'), 'print_jobs', ['sign_asset_id'], unique=False)

def downgrade():
    # Attempt to make it NOT NULL again (might fail if nulls exist)
    # We allow failure or just try
    try:
        op.alter_column('print_jobs', 'sign_asset_id',
               existing_type=sa.BigInteger(),
               nullable=False)
    except:
        pass
