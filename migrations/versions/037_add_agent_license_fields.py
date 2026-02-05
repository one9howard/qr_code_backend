"""add agent license fields

Revision ID: 037
Revises: 036
Create Date: 2026-02-04 17:45:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '037'
down_revision = '036'
branch_labels = None
depends_on = None


def upgrade():
    # Add new columns to agents table
    # Safe check not strictly needed for postgres but good tool practice, 
    # though alembic usually assumes state. We'll just do add_column.
    
    op.add_column('agents', sa.Column('license_number', sa.Text(), nullable=True))
    op.add_column('agents', sa.Column('state', sa.String(2), nullable=True))


def downgrade():
    op.drop_column('agents', 'state')
    op.drop_column('agents', 'license_number')
