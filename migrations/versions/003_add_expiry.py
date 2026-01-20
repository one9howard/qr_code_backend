"""Add expiration and lead notifications

Revision ID: 003
Revises: 002
Create Date: 2026-01-12 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None

def upgrade():
    # 1. Add expires_at to properties
    op.add_column('properties', sa.Column('expires_at', sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column('properties', 'expires_at')
