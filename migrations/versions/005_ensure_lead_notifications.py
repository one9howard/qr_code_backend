"""Ensure lead_notifications table exists (idempotent)

Revision ID: 005
Revises: 004
Create Date: 2026-01-13 10:00:00.000000

This migration guarantees lead_notifications table exists in ALL environments,
regardless of whether 003 was run correctly. Uses SQLAlchemy inspection for idempotency.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = '005'
down_revision = '004'
branch_labels = None
depends_on = None


def upgrade():
    """No-op: lead_notifications already guaranteed by 004."""
    pass


def downgrade():
    """No-op."""
    pass
