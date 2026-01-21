"""listing_kits_mvp

Revision ID: 015
Revises: 014
Create Date: 2026-01-21 07:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '015'
down_revision = '014'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'listing_kits',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('property_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.Text(), nullable=False, server_default='pending'),
        sa.Column('kit_zip_path', sa.Text(), nullable=True),
        sa.Column('flyer_pdf_path', sa.Text(), nullable=True),
        sa.Column('social_square_path', sa.Text(), nullable=True),
        sa.Column('social_story_path', sa.Text(), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['property_id'], ['properties.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('property_id', name='uq_listing_kits_property_id')
    )


def downgrade():
    op.drop_table('listing_kits')
