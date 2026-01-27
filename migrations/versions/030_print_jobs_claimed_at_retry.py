"""print_jobs_claimed_at_retry

Revision ID: 030_print_jobs_retry
Revises: 029_async_jobs_retry
Create Date: 2026-01-26 10:05:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '030_print_jobs_retry'
down_revision = '029_async_jobs_retry'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c['name'] for c in inspector.get_columns('print_jobs')]
    indexes = [i['name'] for i in inspector.get_indexes('print_jobs')]

    # claimed_at triggers reclaim logic if stuck
    if 'claimed_at' not in columns:
        op.add_column('print_jobs', sa.Column('claimed_at', sa.DateTime(), nullable=True))
    
    # next_retry_at for explicit backoff
    # Note: next_retry_at was mentioned in comments as possibly existing. Check it.
    if 'last_error' not in columns:
         op.add_column('print_jobs', sa.Column('last_error', sa.Text(), nullable=True))

    # Add index for efficient claim query
    if 'idx_print_jobs_queue' not in indexes:
        op.create_index('idx_print_jobs_queue', 'print_jobs', ['status', 'next_retry_at'])


def downgrade():
    op.drop_index('idx_print_jobs_queue', table_name='print_jobs')
    op.drop_column('print_jobs', 'last_error')
    op.drop_column('print_jobs', 'claimed_at')
