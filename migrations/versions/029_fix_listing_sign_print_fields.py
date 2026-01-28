"""Fix listing sign print fields normalization

Revision ID: 029
Revises: 028
Create Date: 2026-01-28 07:00:00

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '029'
down_revision = '028'
branch_labels = None
depends_on = None


def upgrade():
    # Normalize historical/bad values produced by early migrations and legacy code.
    # Targets listing sign orders that stored a SKU-like value in print_product or used 'coroplast'/'aluminum'.
    op.execute(
        """
        UPDATE orders
        SET
            -- Canonical order_type bucket
            order_type = CASE WHEN order_type = 'listing_sign' THEN 'sign' ELSE order_type END,

            -- Canonical print_product
            print_product = CASE
                WHEN print_product LIKE 'listing_sign_%' AND print_product <> 'listing_sign' THEN 'listing_sign'
                WHEN print_product IS NULL AND order_type IN ('sign', 'listing_sign') THEN 'listing_sign'
                ELSE print_product
            END,

            -- Canonical material
            material = CASE
                WHEN material IN ('coroplast', 'coroplast_4mm') THEN 'coroplast_4mm'
                WHEN material IN ('aluminum', 'aluminum_040') THEN 'aluminum_040'

                -- Infer when material is missing but we have legacy SKU-ish print_product
                WHEN material IS NULL AND print_product LIKE 'listing_sign_coroplast_%' THEN 'coroplast_4mm'
                WHEN material IS NULL AND print_product LIKE 'listing_sign_aluminum_%' THEN 'aluminum_040'

                ELSE material
            END,

            -- Sides default
            sides = COALESCE(sides, 'single'),

            -- Fill print_size when missing
            print_size = COALESCE(
                print_size,
                CASE
                    WHEN print_product LIKE 'listing_sign_%' AND split_part(print_product, '_', 4) <> '' THEN split_part(print_product, '_', 4)
                    ELSE NULL
                END,
                sign_size
            ),

            updated_at = NOW()
        WHERE
            (print_product LIKE 'listing_sign_%' AND print_product <> 'listing_sign')
            OR material IN ('coroplast', 'aluminum')
            OR (order_type = 'listing_sign')
        """
    )


def downgrade():
    # Non-reversible normalization (best-effort no-op)
    pass
