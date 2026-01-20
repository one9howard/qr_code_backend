"""print_jobs_stabilization

Revision ID: 012
Revises: 011
Create Date: 2026-01-20 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
# Removed invalid import: from sqlalchemy.engine.reflection import Inspector

# revision identifiers, used by Alembic.
revision = '012'
down_revision = '011'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Add missing columns (excluding those in 002: shipping_json, attempts, next_retry_at)
    op.add_column('print_jobs', sa.Column('claimed_by', sa.Text(), nullable=True))
    op.add_column('print_jobs', sa.Column('claimed_at', sa.DateTime(), nullable=True))
    op.add_column('print_jobs', sa.Column('downloaded_at', sa.DateTime(), nullable=True))
    op.add_column('print_jobs', sa.Column('printed_at', sa.DateTime(), nullable=True))
    op.add_column('print_jobs', sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False))
    op.add_column('print_jobs', sa.Column('last_error', sa.Text(), nullable=True))
    
    # 002 added attempts as nullable=True. 012 wants nullable=False.
    # We alter it.
    op.alter_column('print_jobs', 'attempts',
                    existing_type=sa.Integer(),
                    nullable=False,
                    server_default='0')

    # 2. Add Index on status if likely needed for queuing
    op.create_index(op.f('ix_print_jobs_status'), 'print_jobs', ['status'], unique=False)
        
    # 4. Check status column existence
    # Note: 001 already has 'status' (nullable=False). 
    # If 001 ran, print_jobs has status.
    # If we add it again -> Error.
    # But 001 defines it. So we REMOVE this add_column if 001 has it.
    # The previous code checked 'if status not in cols'. 
    # Since 001 creates print_jobs with status, this block was likely dead code.
    # I will comment it out to be safe.
    # op.add_column('print_jobs', sa.Column('status', sa.Text(), server_default='queued', nullable=False))


def downgrade():
    # Simplify downgrade: drop if exists
    # Note: verify support for 'if_exists' in drop_column for target DB, or catch error.
    # Alembic/SQLAlchemy abstract this usually, but safe usage is best.
    
    op.drop_index(op.f('ix_print_jobs_status'), table_name='print_jobs')
    
    op.drop_column('print_jobs', 'attempts')
    op.drop_column('print_jobs', 'last_error')
    
    # updated_at might be critical, but we drop it for full reversion
    op.drop_column('print_jobs', 'updated_at')
    
    op.drop_column('print_jobs', 'printed_at')
    op.drop_column('print_jobs', 'downloaded_at')
    op.drop_column('print_jobs', 'claimed_at')
    op.drop_column('print_jobs', 'claimed_by')
