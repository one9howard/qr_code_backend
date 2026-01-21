"""Phase 5: Print Productization – SKU + PDF Generation + Validation.

Hard requirements validated here:
- Listing Signs: coroplast_4mm OR aluminum_040, single OR double.
- SmartSigns: aluminum_040 ONLY, single OR double.
- SmartSign layouts are restricted to the catalog.
- SmartSign design payload is strictly validated.

Note: These tests rely on the existing `db` fixture (real Postgres) and should be run as part of
`pytest -q` in CI.
"""

import io
import pytest
from PyPDF2 import PdfReader


@pytest.fixture
def paid_order(db):
    """Create a minimal paid Listing Sign order + linked user/agent/property."""
    user_id = db.execute(
        "INSERT INTO users (email, password_hash) VALUES ('sku@test.com', 'hash') RETURNING id"
    ).fetchone()["id"]

    agent_id = db.execute(
        """
        INSERT INTO agents (user_id, name, brokerage, email, phone)
        VALUES (%s, 'Test Agent', 'Test Brokerage', 'agent@test.com', '555-0000')
        RETURNING id
        """,
        (user_id,),
    ).fetchone()["id"]

    prop_id = db.execute(
        """
        INSERT INTO properties (agent_id, address, beds, baths, sqft, price, qr_code)
        VALUES (%s, '123 SK St', '3', '2', '1500', '$499,000', 'sku-qr')
        RETURNING id
        """,
        (agent_id,),
    ).fetchone()["id"]

    order_id = db.execute(
        """
        INSERT INTO orders (user_id, property_id, status, order_type, created_at)
        VALUES (%s, %s, 'paid', 'sign', NOW())
        RETURNING id
        """,
        (user_id, prop_id),
    ).fetchone()["id"]

    db.commit()
    return dict(db.execute("SELECT * FROM orders WHERE id=%s", (order_id,)).fetchone())


# --- SKU Validation ---

def test_listing_sign_allows_coroplast_and_aluminum():
    from services.print_catalog import validate_sku

    ok, _ = validate_sku("listing_sign", "coroplast_4mm", "single")
    assert ok

    ok, _ = validate_sku("listing_sign", "aluminum_040", "double")
    assert ok


def test_smartsign_requires_aluminum_only():
    from services.print_catalog import validate_sku

    ok, reason = validate_sku("smart_sign", "coroplast_4mm", "single")
    assert not ok
    assert "Invalid material" in reason


# --- Listing Sign PDF Generation ---

def test_listing_sign_single_generates_one_page_pdf(db, paid_order):
    from services.printing.listing_sign import generate_listing_sign_pdf

    order = dict(paid_order)
    order.update(
        {
            "print_product": "listing_sign",
            "material": "coroplast_4mm",
            "sides": "single",
            "sign_size": "18x24",
            # Optional payload; generator can fall back to property/user.
            "design_payload": {"sign_color": "#000000"},
        }
    )

    pdf_bytes = generate_listing_sign_pdf(db, order)
    assert pdf_bytes[:4] == b"%PDF"

    reader = PdfReader(io.BytesIO(pdf_bytes))
    assert len(reader.pages) == 1


def test_listing_sign_double_generates_two_page_pdf(db, paid_order):
    from services.printing.listing_sign import generate_listing_sign_pdf

    order = dict(paid_order)
    order.update(
        {
            "print_product": "listing_sign",
            "material": "aluminum_040",
            "sides": "double",
            "sign_size": "18x24",
            "design_payload": {"sign_color": "#FF0000"},
        }
    )

    pdf_bytes = generate_listing_sign_pdf(db, order)
    reader = PdfReader(io.BytesIO(pdf_bytes))
    assert len(reader.pages) == 2


# --- SmartSign Validation + Generation ---

def test_smartsign_invalid_payload_rejected():
    from services.printing.validation import validate_smartsign_payload

    # Invalid banner color id
    errors = validate_smartsign_payload("smart_v1_minimal", {"banner_color_id": "purple"})
    assert any("banner_color_id" in e for e in errors)

    # Too long name
    payload = {"banner_color_id": "blue", "agent_name": "A" * 41, "agent_phone": "123"}
    errors = validate_smartsign_payload("smart_v1_minimal", payload)
    assert any("agent_name exceeds" in e for e in errors)

    # Missing phone
    payload = {"banner_color_id": "blue", "agent_name": "Valid"}
    errors = validate_smartsign_payload("smart_v1_minimal", payload)
    assert any("agent_phone is required" in e for e in errors)


def test_smartsign_layouts_generate_pdf(db, paid_order):
    from services.printing.smart_sign import generate_smart_sign_pdf

    base = dict(paid_order)
    base.update(
        {
            "print_product": "smart_sign",
            "material": "aluminum_040",
            "sides": "single",
            "design_payload": {
                "banner_color_id": "blue",
                "agent_name": "Test Agent",
                "agent_phone": "555-1234",
            },
        }
    )

    layouts = [
        "smart_v1_photo_banner",
        "smart_v1_minimal",
        "smart_v1_agent_brand",
    ]

    for layout in layouts:
        order = dict(base)
        order["layout_id"] = layout
        pdf_bytes = generate_smart_sign_pdf(db, order)
        assert pdf_bytes[:4] == b"%PDF"
        reader = PdfReader(io.BytesIO(pdf_bytes))
        assert len(reader.pages) == 1


def test_smartsign_double_generates_two_pages(db, paid_order):
    from services.printing.smart_sign import generate_smart_sign_pdf

    order = dict(paid_order)
    order.update(
        {
            "print_product": "smart_sign",
            "material": "aluminum_040",
            "sides": "double",
            "layout_id": "smart_v1_minimal",
            "design_payload": {"banner_color_id": "black", "agent_name": "A", "agent_phone": "1"},
        }
    )

    pdf_bytes = generate_smart_sign_pdf(db, order)
    reader = PdfReader(io.BytesIO(pdf_bytes))
    assert len(reader.pages) == 2
