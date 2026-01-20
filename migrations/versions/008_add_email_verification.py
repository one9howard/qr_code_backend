"""Add email verification columns to users table

Revision ID: 008_add_email_verification
Revises: 007_add_order_type
Create Date: 2026-01-15 10:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '008_add_email_verification'
down_revision = '007_add_order_type'
branch_labels = None
depends_on = None


def upgrade():
    # Helper to check if column exists before adding (idempotent-ish)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c['name'] for c in inspector.get_columns('users')]

    if 'verification_code' not in columns:
        op.add_column('users', sa.Column('verification_code', sa.String(length=6), nullable=True))
    
    if 'verification_code_expires_at' not in columns:
        op.add_column('users', sa.Column('verification_code_expires_at', sa.DateTime(), nullable=True))
        
    if 'is_verified' not in columns:
        op.add_column('users', sa.Column('is_verified', sa.Boolean(), server_default='0', nullable=False))


def downgrade():
    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_column('is_verified')
        batch_op.drop_column('verification_code_expires_at')
        batch_op.drop_column('verification_code')
