"""initial_schema

Revision ID: 001
Revises: 
Create Date: 2026-01-10 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # --- Users ---
    op.create_table('users',
        sa.Column('id', sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('password_hash', sa.String(), nullable=False),
        sa.Column('is_verified', sa.Boolean(), server_default='0', nullable=True),
        sa.Column('is_admin', sa.Boolean(), server_default='0', nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('stripe_customer_id', sa.String(), nullable=True),
        sa.Column('stripe_subscription_id', sa.String(), nullable=True),
        sa.Column('subscription_status', sa.String(), server_default='free', nullable=True),
        sa.Column('subscription_end_date', sa.DateTime(), nullable=True),
        sa.Column('full_name', sa.String(), nullable=True),
        sa.Column('username', sa.String(), nullable=True),
        sa.UniqueConstraint('email')
    )

    # --- Agents ---
    op.create_table('agents',
        sa.Column('id', sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('brokerage', sa.String(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('phone', sa.String(), nullable=True),
        sa.Column('photo_filename', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], )
    )

    # --- Properties ---
    op.create_table('properties',
        sa.Column('id', sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column('agent_id', sa.Integer(), nullable=False),
        sa.Column('address', sa.String(), nullable=False),
        sa.Column('beds', sa.String(), nullable=False),
        sa.Column('baths', sa.String(), nullable=False),
        sa.Column('sqft', sa.String(), nullable=True),
        sa.Column('price', sa.String(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('slug', sa.String(), nullable=True),
        sa.Column('qr_code', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], )
    )
    op.create_index('idx_properties_qr_code', 'properties', ['qr_code'], unique=True)

    # --- Property Photos ---
    op.create_table('property_photos',
        sa.Column('id', sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column('property_id', sa.Integer(), nullable=False),
        sa.Column('filename', sa.String(), nullable=False),
        sa.ForeignKeyConstraint(['property_id'], ['properties.id'], )
    )

    # --- QR Scans ---
    op.create_table('qr_scans',
        sa.Column('id', sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column('property_id', sa.Integer(), nullable=False),
        sa.Column('scanned_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('ip_address', sa.String(), nullable=True),
        sa.Column('user_agent', sa.String(), nullable=True),
        sa.Column('utm_source', sa.String(), nullable=True),
        sa.Column('utm_medium', sa.String(), nullable=True),
        sa.Column('utm_campaign', sa.String(), nullable=True),
        sa.Column('referrer', sa.String(), nullable=True),
        sa.Column('visitor_hash', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['property_id'], ['properties.id'], )
    )

    # --- Stripe Events (Text PK, no change) ---
    op.create_table('stripe_events',
        sa.Column('event_id', sa.String(), nullable=False),
        sa.Column('type', sa.String(), nullable=False),
        sa.Column('status', sa.String(), server_default='received', nullable=True),
        sa.Column('last_error', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('event_id')
    )

    # --- Orders ---
    op.create_table('orders',
        sa.Column('id', sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('guest_email', sa.String(), nullable=True),
        sa.Column('property_id', sa.Integer(), nullable=False),
        sa.Column('sign_pdf_path', sa.String(), nullable=True),
        sa.Column('status', sa.String(), server_default='pending_payment', nullable=True),
        sa.Column('stripe_checkout_session_id', sa.String(), nullable=True),
        sa.Column('stripe_payment_intent_id', sa.String(), nullable=True),
        sa.Column('stripe_customer_id', sa.String(), nullable=True),
        sa.Column('shipping_address', sa.String(), nullable=True),
        sa.Column('tracking_number', sa.String(), nullable=True),
        sa.Column('paid_at', sa.DateTime(), nullable=True),
        sa.Column('submitted_at', sa.DateTime(), nullable=True),
        sa.Column('fulfilled_at', sa.DateTime(), nullable=True),
        sa.Column('fulfillment_error', sa.String(), nullable=True),
        sa.Column('provider_job_id', sa.String(), nullable=True),
        sa.Column('guest_token', sa.String(), nullable=True),
        sa.Column('guest_token_created_at', sa.DateTime(), nullable=True),
        sa.Column('sign_color', sa.String(), server_default='#1F6FEB', nullable=True),
        sa.Column('sign_size', sa.String(), server_default='18x24', nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('print_idempotency_key', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['property_id'], ['properties.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], )
    )
    op.create_index('idx_orders_guest_token', 'orders', ['guest_token'], unique=False)

    # --- Checkout Attempts ---
    op.create_table('checkout_attempts',
        sa.Column('id', sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column('attempt_token', sa.String(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('purpose', sa.String(), nullable=False),
        sa.Column('status', sa.String(), server_default='created', nullable=False),
        sa.Column('idempotency_key', sa.String(), nullable=False),
        sa.Column('stripe_session_id', sa.String(), nullable=True),
        sa.Column('stripe_customer_id', sa.String(), nullable=True),
        sa.Column('params_hash', sa.String(), nullable=False),
        sa.Column('error_message', sa.String(), nullable=True),
        sa.Column('created_at', sa.String(), nullable=False),
        sa.Column('updated_at', sa.String(), nullable=False),
        sa.Column('order_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.UniqueConstraint('attempt_token'),
        sa.UniqueConstraint('idempotency_key')
    )
    op.create_index('idx_checkout_attempts_token', 'checkout_attempts', ['attempt_token'], unique=False)
    op.create_index('idx_checkout_attempts_user', 'checkout_attempts', ['user_id', 'purpose', 'created_at'], unique=False)
    op.create_index('idx_checkout_attempts_order', 'checkout_attempts', ['order_id', 'purpose', 'created_at'], unique=False)

    # --- Order Agent Snapshot ---
    op.create_table('order_agent_snapshot',
        sa.Column('id', sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column('order_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('brokerage', sa.String(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('phone', sa.String(), nullable=True),
        sa.Column('photo_filename', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ),
        sa.UniqueConstraint('order_id')
    )

    # --- Leads ---
    op.create_table('leads',
        sa.Column('id', sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column('property_id', sa.Integer(), nullable=False),
        sa.Column('agent_id', sa.Integer(), nullable=False),
        sa.Column('buyer_name', sa.String(), nullable=False),
        sa.Column('buyer_email', sa.String(), nullable=False),
        sa.Column('buyer_phone', sa.String(), nullable=True),
        sa.Column('preferred_contact', sa.String(), server_default='call', nullable=True),
        sa.Column('best_time', sa.String(), nullable=True),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('consent_given', sa.Boolean(), server_default='1', nullable=True),
        sa.Column('status', sa.String(), server_default='new', nullable=True),
        sa.Column('ip_address', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ),
        sa.ForeignKeyConstraint(['property_id'], ['properties.id'], )
    )
    op.create_index('idx_leads_agent', 'leads', ['agent_id', 'created_at'], unique=False)

    # --- Property Views ---
    op.create_table('property_views',
        sa.Column('id', sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column('property_id', sa.Integer(), nullable=False),
        sa.Column('viewed_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('ip_address', sa.String(), nullable=True),
        sa.Column('user_agent', sa.String(), nullable=True),
        sa.Column('referrer', sa.String(), nullable=True),
        sa.Column('is_internal', sa.Integer(), server_default='0', nullable=True),
        sa.Column('source', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['property_id'], ['properties.id'], )
    )
    op.create_index('idx_property_views_property', 'property_views', ['property_id', 'viewed_at'], unique=False)
    op.create_index('idx_property_views_internal', 'property_views', ['property_id', 'is_internal', 'viewed_at'], unique=False)

    # --- Print Jobs (Text PK, no change) ---
    op.create_table('print_jobs',
        sa.Column('idempotency_key', sa.String(), nullable=False),
        sa.Column('job_id', sa.String(), nullable=False),
        sa.Column('order_id', sa.Integer(), nullable=True),
        sa.Column('filename', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.PrimaryKeyConstraint('idempotency_key')
    )


def downgrade():
    op.drop_table('print_jobs')
    op.drop_table('property_views')
    op.drop_table('leads')
    op.drop_table('order_agent_snapshot')
    op.drop_table('checkout_attempts')
    op.drop_table('orders')
    op.drop_table('stripe_events')
    op.drop_table('qr_scans')
    op.drop_table('property_photos')
    op.drop_table('properties')
    op.drop_table('agents')
    op.drop_table('users')
