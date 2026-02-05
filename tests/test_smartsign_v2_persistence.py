import pytest
import json
from unittest.mock import MagicMock, patch
from services.orders import process_paid_order
from services.pdf_smartsign import generate_smartsign_pdf
from database import get_db

@pytest.fixture
def mock_storage():
    with patch('services.pdf_smartsign.get_storage') as mock:
        storage_instance = MagicMock()
        mock.return_value = storage_instance
        # Mock put_file to just return a fake key
        storage_instance.put_file.return_value = 'mock_key.pdf'
        yield storage_instance

def test_smartsign_v2_persistence_e2e(app, db, mock_storage):
    """
    Test that SmartSign V2 fields are persisted from Order Payload -> Sign Asset,
    and then correctly rendered in the PDF.
    """
    # db fixture already active and provides connection.
    # Logic below uses 'db' variable which is now the fixture argument.
    
    # 1. Setup: Create a User
    # Clean up potentially existing user handling if needed, but pytest rollback usually handles this.
    # Using raw SQL to avoid model dependencies
    db.execute("INSERT INTO users (email, full_name, password_hash) VALUES ('v2_test@example.com', 'V2 Tester', 'dummy_hash') ON CONFLICT DO NOTHING")
    user = db.execute("SELECT id FROM users WHERE email = 'v2_test@example.com'").fetchone()
    user_id = user['id']

    # 2. Setup: Create an Order with V2 Payload
    payload = {
        "code": "PERSISTTEST",
        "agent_name": "Persisted Name",
        "agent_phone": "555-999-0000",
        "state": "XY",
        "license_number": "LIC-9999",
        "show_license_option": "show",
        "license_label_override": "LicID",
        # Legacy/Fallback keys to ensure preference
        "brand_name": "Legacy Brand",
        "phone": "555-000-0000",
        "layout_id": "smart_v2_vertical_banner"
    }
    
    order_res = db.execute("""
        INSERT INTO orders (user_id, order_type, status, amount_total_cents, design_payload, print_size)
        VALUES (%s, 'smart_sign', 'pending', 5000, %s, '18x24')
        RETURNING id
    """, (user_id, json.dumps(payload)))
    order_id = order_res.fetchone()['id']
    
    # 3. Simulate Stripe Webhook Session
    session = {
        "id": "cs_test_v2_persistence",
        "payment_status": "paid",
        "amount_total": 5000,
        "currency": "usd",
        "customer": "cus_test_v2",
        "metadata": {
            "order_id": str(order_id),
            "purpose": "smart_sign"
        }
    }
    
    # 4. Process Paid Order (The Core Persistence Logic)
    process_paid_order(db, session)
    
    # 5. Assert: Verify DB Persistence
    asset = db.execute("""
        SELECT * FROM sign_assets 
        WHERE activation_order_id = %s
    """, (order_id,)).fetchone()
    
    assert asset is not None, "Sign Asset should be created"
    assert asset['agent_name'] == "Persisted Name"
    assert asset['agent_phone'] == "555-999-0000"  # Should prioritize payload['agent_phone']
    assert asset['state'] == "XY"
    assert asset['license_number'] == "LIC-9999"
    assert asset['show_license_option'] == "show"
    assert asset['license_label_override'] == "LicID"
    
    # 6. Assert: PDF Generation Logic (Reading from Asset)
    # We call generate_smartsign_pdf directly with the asset
    # We need to ensure it uses the V2 layout where these fields are used.
    
    asset_dict = dict(asset)
    asset_dict['layout_id'] = 'smart_v2_vertical_banner'
    asset_dict['print_size'] = '18x24'
    
    # Use a real file capture execution to check PDF text?
    # Or just rely on code inspection? User asked:
    # "Call fulfillment PDF generation... and assert... extracted text contains..."
    # This implies we need to actually run the PDF generation and inspect output.
    
    # To do this without uploading to valid storage key, we can intercept the buffer
    # But generate_smartsign_pdf internals write to BytesIO and then call storage.save(key, buffer, type)
    
    # We can mock storage.save and inspect the arguments
    
    generate_smartsign_pdf(asset_dict, order_id)
    
    # Get the bytes from the mock call
    mock_storage.put_file.assert_called()
    call_args = mock_storage.put_file.call_args
    # args: (data, key, content_type)
    
    file_data = call_args[0][0]
    if hasattr(file_data, 'getvalue'):
        pdf_bytes = file_data.getvalue()
    else:
        pdf_bytes = file_data
        
    # Extract Text using PyMuPDF (fitz)
    import fitz
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    text = ""
    for page in doc:
        text += page.get_text()
        
    print(f"DEBUG: Extracted PDF Text:\n{text}")
    
    assert "Persisted Name" in text
    assert "555-999-0000" in text
    assert "LicID" in text
    assert "LIC-9999" in text
    
    # Verify Legacy Fallback NOT used
    assert "Legacy Brand" not in text
