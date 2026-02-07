"""Add unique constraint on properties.slug for ON CONFLICT support.

Revision ID: 040
Revises: 039
Create Date: 2026-02-07
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '040'
down_revision = '039'
branch_labels = None
depends_on = None


def upgrade():
    # Add unique constraint on properties.slug (needed for ON CONFLICT)
    op.create_unique_constraint('uq_properties_slug', 'properties', ['slug'])


def downgrade():
    op.drop_constraint('uq_properties_slug', 'properties', type_='unique')
