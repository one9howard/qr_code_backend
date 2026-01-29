"""add scheduling and virtual tour urls

Revision ID: 034_add_scheduling_and_virtual_tour_urls
Revises: 033_fix_ls_print
Create Date: 2026-01-29 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '034_scheduling_tour_urls'
down_revision = '033_fix_ls_print'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('agents', sa.Column('scheduling_url', sa.Text(), nullable=True))
    op.add_column('properties', sa.Column('virtual_tour_url', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('properties', 'virtual_tour_url')
    op.drop_column('agents', 'scheduling_url')
