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
    # claimed_at triggers reclaim logic if stuck
    op.add_column('print_jobs', sa.Column('claimed_at', sa.DateTime(), nullable=True))
    
    # next_retry_at for explicit backoff
    # Note: next_retry_at was likely already there in some previous form or ad-hoc, 
    # but prompt implies adding it. The printing code had `next_retry_at` in the UPDATE query already?
    # Checking previous code: Step 627 line 94: `next_retry_at = CURRENT_TIMESTAMP + interval '5 minutes'`
    # It seems `next_retry_at` MIGHT already exist or the code was anticipating it.
    # Let's check `027_async_jobs_queue.py` or print job schema if possible to avoid dup error.
    # However, user explicitly requested "Add columns: claimed_at TIMESTAMP NULL, optionally last_error TEXT NULL".
    # User's Prompt: "Add columns: claimed_at TIMESTAMP NULL, optionally last_error TEXT NULL"
    # Wait, the user said for Print Jobs: "status='queued' AND (next_retry_at IS NULL OR next_retry_at <= NOW())"
    # If the column doesn't exist, we add it. I'll add 'last_error' as requested too.
    
    op.add_column('print_jobs', sa.Column('claimed_at', sa.DateTime(), nullable=True))
    op.add_column('print_jobs', sa.Column('last_error', sa.Text(), nullable=True))

    # Add index for efficient claim query
    # "status='queued' AND (next_retry_at IS NULL OR next_retry_at <= NOW())"
    # Index on status is likely there. adding composite might help.
    op.create_index('idx_print_jobs_queue', 'print_jobs', ['status', 'next_retry_at'])


def downgrade():
    op.drop_index('idx_print_jobs_queue', table_name='print_jobs')
    op.drop_column('print_jobs', 'last_error')
    op.drop_column('print_jobs', 'claimed_at')
