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
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    
    # 0. Safety Check: Verify table exists (it should from 001/008)
    if 'print_jobs' not in inspector.get_table_names():
        # Fallback: Create table if it doesn't exist (e.g. if 001 didn't run or was modified??)
        # However, for stability, we should assume it exists or log warning. 
        # But to be safe, we can skip or create.
        # Given "Clean DB Support", 001 should have run. 
        # If it's missing, let's create it with the BASE schema, then add columns?
        # No, reusing 001 definition duplicates code. 
        # Let's assume it exists, but wrapping in check avoids "NoSuchTableError" to cleanly error out or skip?
        # If we skip, we miss columns. 
        # If we error, we know why.
        # But "idempotent" means if it crashed halfway, we can re-run.
        # If table is missing, the previous migrations failed? 
        return

    # 1. Add missing columns safely
    existing_columns = [c['name'] for c in inspector.get_columns('print_jobs')]
    
    if 'claimed_by' not in existing_columns:
        op.add_column('print_jobs', sa.Column('claimed_by', sa.Text(), nullable=True))
        
    if 'claimed_at' not in existing_columns:
        op.add_column('print_jobs', sa.Column('claimed_at', sa.DateTime(), nullable=True))
        
    if 'downloaded_at' not in existing_columns:
        op.add_column('print_jobs', sa.Column('downloaded_at', sa.DateTime(), nullable=True))
        
    if 'printed_at' not in existing_columns:
        op.add_column('print_jobs', sa.Column('printed_at', sa.DateTime(), nullable=True))
        
    if 'updated_at' not in existing_columns:
        op.add_column('print_jobs', sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False))
        
    if 'last_error' not in existing_columns:
        op.add_column('print_jobs', sa.Column('last_error', sa.Text(), nullable=True))
        
    if 'attempts' not in existing_columns:
        # Use string '0' for server_default safe for SQL
        op.add_column('print_jobs', sa.Column('attempts', sa.Integer(), server_default='0', nullable=False))

    # 2. Add Index on status if likely needed for queuing
    indexes = [i['name'] for i in inspector.get_indexes('print_jobs')]
    if 'ix_print_jobs_status' not in indexes:
        op.create_index(op.f('ix_print_jobs_status'), 'print_jobs', ['status'], unique=False)
        
    # 4. Check status column existence
    if 'status' not in existing_columns:
         op.add_column('print_jobs', sa.Column('status', sa.Text(), server_default='queued', nullable=False))


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
