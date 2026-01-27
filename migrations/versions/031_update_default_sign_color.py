"""update default sign color

Revision ID: 031_update_default_sign_color
Revises: 030_print_jobs_claimed_at_retry
Create Date: 2026-01-26 19:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '031_update_default_sign_color'
down_revision = '030_print_jobs_retry'
branch_labels = None
depends_on = None


def upgrade():
    # Update default value for sign_color column in orders table
    op.alter_column('orders', 'sign_color', server_default='#0077ff')
    
    # Optional backfill for NULLs (if any exist where they should have a color)
    # But usually sign_color is nullable only if not set?
    # Prompt: "Optionally: update existing rows where sign_color is NULL to #0077ff"
    op.execute("UPDATE orders SET sign_color = '#0077ff' WHERE sign_color IS NULL")


def downgrade():
    op.alter_column('orders', 'sign_color', server_default='#1F6FEB')
