"""Print Jobs Drift Fix (shipping_json, next_retry_at)

Revision ID: 013_print_jobs_drift_fix
Revises: 012
Create Date: 2026-01-20 18:40:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '013_print_jobs_drift_fix'
down_revision = '012' 
branch_labels = None
depends_on = None

def upgrade():
    # shipping_json and next_retry_at are in 002.
    # checking logic removed. 
    pass


def downgrade():
    op.drop_column('print_jobs', 'next_retry_at')
    op.drop_column('print_jobs', 'shipping_json')
    # We do NOT drop attempts as 012 added it (technically)
