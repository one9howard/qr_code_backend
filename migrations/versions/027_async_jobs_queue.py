"""async_jobs_queue

Revision ID: 027
Revises: 026
Create Date: 2026-01-25 12:00:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '027'
down_revision = '026'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        'async_jobs',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('job_type', sa.Text(), nullable=False),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('status', sa.Text(), server_default='queued', nullable=False),
        sa.Column('attempts', sa.Integer(), server_default='0', nullable=False),
        sa.Column('locked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_async_jobs_status_created', 'async_jobs', ['status', 'created_at'], unique=False)
    op.create_index('ix_async_jobs_type_status', 'async_jobs', ['job_type', 'status'], unique=False)

def downgrade():
    op.drop_index('ix_async_jobs_type_status', table_name='async_jobs')
    op.drop_index('ix_async_jobs_status_created', table_name='async_jobs')
    op.drop_table('async_jobs')
