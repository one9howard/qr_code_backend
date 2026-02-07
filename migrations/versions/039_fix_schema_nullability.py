"""Make beds, baths, and qr_scans.property_id nullable to fix test contract.

Revision ID: 039_fix_schema_nullability
Revises: 038_rename_listing_to_yard_sign
Create Date: 2026-02-07
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '039'
down_revision = '038'
branch_labels = None
depends_on = None


def upgrade():
    # Make properties.beds nullable
    op.alter_column('properties', 'beds',
        existing_type=sa.INTEGER(),
        nullable=True
    )
    
    # Make properties.baths nullable
    op.alter_column('properties', 'baths',
        existing_type=sa.REAL(),  # baths is typically REAL for values like 1.5
        nullable=True
    )
    
    # Make qr_scans.property_id nullable (for unassigned SmartSign scans)
    op.alter_column('qr_scans', 'property_id',
        existing_type=sa.INTEGER(),
        nullable=True
    )


def downgrade():
    # Re-applying NOT NULL is unsafe if NULL data exists.
    # Raise explicit error to prevent accidental data loss.
    raise RuntimeError(
        "Downgrade blocked: Cannot re-apply NOT NULL to 'beds', 'baths', "
        "or 'qr_scans.property_id' without first cleaning up NULL values. "
        "Manual intervention required."
    )
