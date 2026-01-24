"""add qr_logo fields

Revision ID: 024
Revises: 023
Create Date: 2026-01-24 18:45:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '024'
down_revision = '023'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('qr_logo_original_key', sa.Text(), nullable=True))
    op.add_column('users', sa.Column('qr_logo_normalized_key', sa.Text(), nullable=True))
    op.add_column('users', sa.Column('use_qr_logo', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('users', sa.Column('qr_logo_updated_at', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column('users', 'qr_logo_updated_at')
    op.drop_column('users', 'use_qr_logo')
    op.drop_column('users', 'qr_logo_normalized_key')
    op.drop_column('users', 'qr_logo_original_key')
