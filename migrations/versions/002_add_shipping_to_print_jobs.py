"""Add shipping to print_jobs

Revision ID: 002
Revises: 001
Create Date: 2026-01-12 09:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('print_jobs', sa.Column('shipping_json', sa.Text(), nullable=True))
    op.add_column('print_jobs', sa.Column('attempts', sa.Integer(), server_default='0', nullable=True))
    op.add_column('print_jobs', sa.Column('next_retry_at', sa.DateTime(), nullable=True))

def downgrade():
    op.drop_column('print_jobs', 'next_retry_at')
    op.drop_column('print_jobs', 'attempts')
    op.drop_column('print_jobs', 'shipping_json')
