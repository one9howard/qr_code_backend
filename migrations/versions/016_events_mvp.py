"""Events table for minimal analytics

Revision ID: 016_events_mvp
Revises: 015_listing_kits_mvp
Create Date: 2026-01-21

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '016'
down_revision = '015'
branch_labels = None
depends_on = None


def upgrade():
    # Create events table for minimal analytics
    op.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            event_name TEXT NOT NULL,
            property_id INTEGER REFERENCES properties(id) ON DELETE SET NULL,
            order_id INTEGER REFERENCES orders(id) ON DELETE SET NULL,
            meta_json JSONB,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    
    # Create indexes for efficient querying
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_events_name_created 
        ON events(event_name, created_at)
    """)
    
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_events_user_created 
        ON events(user_id, created_at)
    """)


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_events_user_created")
    op.execute("DROP INDEX IF EXISTS idx_events_name_created")
    op.execute("DROP TABLE IF EXISTS events")
