"""fix sign_color default safely

Revision ID: 032_fix_sign_color_default
Revises: 031_update_default_sign_color
Create Date: 2026-01-27 10:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '032_fix_sign_color_default'
down_revision = '031_update_default_sign_color'
branch_labels = None
depends_on = None


def upgrade():
    # Safely set the server default using a text literal
    op.alter_column('orders', 'sign_color',
                    server_default=sa.text("'#0077ff'"),
                    existing_type=sa.String(length=7))


def downgrade():
    # Remove the default on downgrade
    op.alter_column('orders', 'sign_color',
                    server_default=None,
                    existing_type=sa.String(length=7))
