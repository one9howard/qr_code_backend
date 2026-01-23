"""Extend App Events (Batch)

Revision ID: 021
Revises: 020
Create Date: 2026-01-22 20:55:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '021'
down_revision = '020'
branch_labels = None
depends_on = None

def upgrade():
    # Use raw SQL with IF NOT EXISTS to handle partial previous runs
    op.execute("ALTER TABLE app_events ADD COLUMN IF NOT EXISTS event_uuid UUID DEFAULT uuid_generate_v4() NOT NULL")
    op.execute("ALTER TABLE app_events ADD COLUMN IF NOT EXISTS received_at TIMESTAMPTZ DEFAULT now() NOT NULL")
    op.execute("ALTER TABLE app_events ADD COLUMN IF NOT EXISTS schema_version INTEGER DEFAULT 1 NOT NULL")
    op.execute("ALTER TABLE app_events ADD COLUMN IF NOT EXISTS environment TEXT DEFAULT 'production' NOT NULL")
    op.execute("ALTER TABLE app_events ADD COLUMN IF NOT EXISTS actor_type TEXT DEFAULT 'system' NOT NULL")
    op.execute("ALTER TABLE app_events ADD COLUMN IF NOT EXISTS actor_id INTEGER")
    op.execute("ALTER TABLE app_events ADD COLUMN IF NOT EXISTS subject_type TEXT")
    op.execute("ALTER TABLE app_events ADD COLUMN IF NOT EXISTS subject_id INTEGER")
    op.execute("ALTER TABLE app_events ADD COLUMN IF NOT EXISTS sign_asset_id INTEGER")
    op.execute("ALTER TABLE app_events ADD COLUMN IF NOT EXISTS order_id INTEGER")
    op.execute("ALTER TABLE app_events ADD COLUMN IF NOT EXISTS session_id TEXT")
    op.execute("ALTER TABLE app_events ADD COLUMN IF NOT EXISTS request_id TEXT")
    op.execute("ALTER TABLE app_events ADD COLUMN IF NOT EXISTS idempotency_key TEXT")
    op.execute("ALTER TABLE app_events ADD COLUMN IF NOT EXISTS ip_hash TEXT")
    op.execute("ALTER TABLE app_events ADD COLUMN IF NOT EXISTS ua_hash TEXT")

    # Indexes - use raw SQL with IF NOT EXISTS
    op.execute("CREATE INDEX IF NOT EXISTS idx_app_events_type_time ON app_events (event_type, occurred_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_app_events_property_time ON app_events (property_id, occurred_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_app_events_user_time ON app_events (user_id, occurred_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_app_events_qr_time ON app_events (qr_code, occurred_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_app_events_subject_time ON app_events (subject_type, subject_id, occurred_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_app_events_actor_time ON app_events (actor_type, actor_id, occurred_at DESC)")
    
    # Unique constraint - check if exists first
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_app_events_idempotency') THEN
                ALTER TABLE app_events ADD CONSTRAINT uq_app_events_idempotency UNIQUE (event_type, idempotency_key);
            END IF;
        END $$;
    """)

def downgrade():
    with op.batch_alter_table('app_events') as batch_op:
        batch_op.drop_constraint('uq_app_events_idempotency', type_='unique')
        batch_op.drop_index('idx_app_events_actor_time')
        batch_op.drop_index('idx_app_events_subject_time')
        batch_op.drop_index('idx_app_events_qr_time')
        batch_op.drop_index('idx_app_events_user_time')
        batch_op.drop_index('idx_app_events_property_time')
        batch_op.drop_index('idx_app_events_type_time')
        
        batch_op.drop_column('ua_hash')
        batch_op.drop_column('ip_hash')
        batch_op.drop_column('idempotency_key')
        batch_op.drop_column('request_id')
        batch_op.drop_column('session_id')
        batch_op.drop_column('order_id')
        batch_op.drop_column('sign_asset_id')
        batch_op.drop_column('subject_id')
        batch_op.drop_column('subject_type')
        batch_op.drop_column('actor_id')
        batch_op.drop_column('actor_type')
        batch_op.drop_column('environment')
        batch_op.drop_column('schema_version')
        batch_op.drop_column('received_at')
        batch_op.drop_column('event_uuid')
