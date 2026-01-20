"""lead management

Revision ID: 006_lead_management
Revises: 005
Create Date: 2026-01-14 19:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = '006_lead_management'
down_revision = '005'
branch_labels = None
depends_on = None

def upgrade():
    conn = op.get_bind()
    inspector = inspect(conn)
    tables = inspector.get_table_names()

    # 1. Enhance leads table (Idempotent)
    leads_columns = [c['name'] for c in inspector.get_columns('leads')]
    
    with op.batch_alter_table('leads', schema=None) as batch_op:
        if 'status' not in leads_columns:
            batch_op.add_column(sa.Column('status', sa.String(length=50), server_default='new', nullable=False))
            batch_op.create_index(batch_op.f('ix_leads_status'), ['status'], unique=False)
        
        if 'last_contacted_at' not in leads_columns:
            batch_op.add_column(sa.Column('last_contacted_at', sa.DateTime(), nullable=True))

    # 2. Create lead_notes table
    if 'lead_notes' not in tables:
        op.create_table('lead_notes',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('lead_id', sa.Integer(), nullable=False),
            sa.Column('actor_user_id', sa.Integer(), nullable=True),
            sa.Column('body', sa.Text(), nullable=False),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
            sa.ForeignKeyConstraint(['lead_id'], ['leads.id'], ),
            sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], ),
            sa.PrimaryKeyConstraint('id')
        )

    # 3. Create lead_tasks table
    if 'lead_tasks' not in tables:
        op.create_table('lead_tasks',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('lead_id', sa.Integer(), nullable=False),
            sa.Column('assigned_to_user_id', sa.Integer(), nullable=True),
            sa.Column('title', sa.String(length=255), nullable=False),
            sa.Column('due_at', sa.DateTime(), nullable=True),
            sa.Column('status', sa.String(length=50), server_default='open', nullable=False),
            sa.Column('completed_at', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
            sa.ForeignKeyConstraint(['lead_id'], ['leads.id'], ),
            sa.ForeignKeyConstraint(['assigned_to_user_id'], ['users.id'], ),
            sa.PrimaryKeyConstraint('id')
        )

    # 4. Create lead_events table (Audit Log)
    if 'lead_events' not in tables:
        op.create_table('lead_events',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('lead_id', sa.Integer(), nullable=False),
            sa.Column('event_type', sa.String(length=100), nullable=False),
            sa.Column('payload', sa.Text(), nullable=True), # Store as text for SQLite compat
            sa.Column('actor_user_id', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
            sa.ForeignKeyConstraint(['lead_id'], ['leads.id'], ),
            sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], ),
            sa.PrimaryKeyConstraint('id')
        )

    # 5. Create campaigns table
    if 'campaigns' not in tables:
        op.create_table('campaigns',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('property_id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=255), nullable=False),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
            sa.ForeignKeyConstraint(['property_id'], ['properties.id'], ),
            sa.PrimaryKeyConstraint('id')
        )

    # 6. Create qr_variants table
    if 'qr_variants' not in tables:
        op.create_table('qr_variants',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('property_id', sa.Integer(), nullable=False),
            sa.Column('campaign_id', sa.Integer(), nullable=True),
            sa.Column('code', sa.String(length=50), nullable=False),
            sa.Column('label', sa.String(length=255), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
            sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ),
            sa.ForeignKeyConstraint(['property_id'], ['properties.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('code', name='uq_qr_variants_code')
        )

    # 7. Add attribution columns to analytics tables (Idempotent)
    qr_scans_columns = [c['name'] for c in inspector.get_columns('qr_scans')]
    with op.batch_alter_table('qr_scans', schema=None) as batch_op:
        if 'qr_variant_id' not in qr_scans_columns:
            batch_op.add_column(sa.Column('qr_variant_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key('fk_qr_scans_qr_variant_id', 'qr_variants', ['qr_variant_id'], ['id'])
        
        if 'campaign_id' not in qr_scans_columns:
            batch_op.add_column(sa.Column('campaign_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key('fk_qr_scans_campaign_id', 'campaigns', ['campaign_id'], ['id'])

    property_views_columns = [c['name'] for c in inspector.get_columns('property_views')]
    with op.batch_alter_table('property_views', schema=None) as batch_op:
        if 'qr_variant_id' not in property_views_columns:
            batch_op.add_column(sa.Column('qr_variant_id', sa.Integer(), nullable=True))
        
        if 'campaign_id' not in property_views_columns:
            batch_op.add_column(sa.Column('campaign_id', sa.Integer(), nullable=True))


def downgrade():
    # Note: Downgrade also needs to be careful if we are in a mixed state, 
    # but usually downgrade is manual. For now, keep standard downgrade logic 
    # but could wrap in try/except or checks if needed.
    # Assuming standard behavior is fine for rollback unless we are really messed up.
    
    with op.batch_alter_table('property_views', schema=None) as batch_op:
        batch_op.drop_column('campaign_id')
        batch_op.drop_column('qr_variant_id')

    with op.batch_alter_table('qr_scans', schema=None) as batch_op:
        batch_op.drop_column('campaign_id')
        batch_op.drop_column('qr_variant_id')
        # batch_op.drop_constraint('fk_qr_scans_qr_variant_id', type_='foreignkey') # SQLite batch handles logic

    op.drop_table('qr_variants')
    op.drop_table('campaigns')
    op.drop_table('lead_events')
    op.drop_table('lead_tasks')
    op.drop_table('lead_notes')

    with op.batch_alter_table('leads', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_leads_status'))
        batch_op.drop_column('last_contacted_at')
        batch_op.drop_column('status')
