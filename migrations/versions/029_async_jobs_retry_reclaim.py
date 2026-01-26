"""async_jobs_retry_reclaim

Revision ID: 029_async_jobs_retry
Revises: 028_canonicalize_orders
Create Date: 2026-01-26 10:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '029_async_jobs_retry'
down_revision = '028_canonicalize_orders'
branch_labels = None
depends_on = None


def upgrade():
    # Add next_run_at for retry scheduling
    op.add_column('async_jobs', sa.Column('next_run_at', sa.DateTime(), nullable=True))
    
    # Add locked_by for improved auditing of who claimed the job
    op.add_column('async_jobs', sa.Column('locked_by', sa.String(), nullable=True))
    
    # Add index on (status, next_run_at) for efficient polling
    op.create_index('idx_async_jobs_status_next_run', 'async_jobs', ['status', 'next_run_at'])


def downgrade():
    op.drop_index('idx_async_jobs_status_next_run', table_name='async_jobs')
    op.drop_column('async_jobs', 'locked_by')
    op.drop_column('async_jobs', 'next_run_at')
