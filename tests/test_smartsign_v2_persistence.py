
import pytest
import json
from services.orders import process_paid_order
from services.fulfillment import _generate_smartsign_pdf
from utils.storage import get_storage
import fitz  # PyMuPDF

class TestSmartSignV2Persistence:

    def test_v2_fields_persistence_and_printing(self, app, db):
        """
        Verify that:
        1. V2 payload fields (agent_name, agent_phone, license, etc.) are persisted to sign_assets.
        2. The generated PDF contains these values.
        """
        # 1. Setup Data
        # User
        db.execute("INSERT INTO users (email, full_name, role) VALUES ('v2test@example.com', 'V2 Tester', 'agent')")
        user_id = db.execute("SELECT id FROM users WHERE email='v2test@example.com'").fetchone()[0]
        
        # V2 Payload
        payload = {
            'print_size': '18x24',
            'layout_id': 'smart_v2_vertical_banner',
            'agent_name': 'Persistence Agent', 
            'agent_phone': '555-9999',   
            'license_number': '12345678', 
            'state': 'CA',               
            'show_license_option': 'show', 
            'license_label_override': 'TestLic:' 
        }
        
        # Create Order
        db.execute("""
            INSERT INTO orders (
                user_id, status, order_type, amount_total_cents, currency, design_payload
            ) VALUES (
                %s, 'pending_payment', 'smart_sign', 5000, 'usd', %s
            )
        """, (user_id, json.dumps(payload)))
        order_id = db.execute("SELECT id FROM orders WHERE user_id=%s ORDER BY id DESC LIMIT 1", (user_id,)).fetchone()[0]
        
        # Mock Session
        session = {
            'id': 'cs_test_v2_persist',
            'metadata': {
                'order_id': order_id,
                'purpose': 'smart_sign'
            },
            'payment_status': 'paid',
            'amount_total': 5000,
            'currency': 'usd',
            'customer': 'cus_test_v2',
            'customer_details': {'email': 'v2test@example.com'},
        }

        # 2. Process Paid Order (Triggers Asset Creation & Persistence)
        process_paid_order(db, session)
        
        # 3. Assert DB Persistence
        asset = db.execute("SELECT * FROM sign_assets WHERE activation_order_id = %s", (order_id,)).fetchone()
        assert asset is not None
        
        print(f"Asset Created: {asset['id']}")
        
        # Check Columns
        assert asset['agent_name'] == 'Persistence Agent'
        assert asset['agent_phone'] == '555-9999'
        assert asset['license_number'] == '12345678'
        assert asset['state'] == 'CA'
        assert asset['show_license_option'] == 'show'
        assert asset['license_label_override'] == 'TestLic:'
        
        # 4. Assert PDF Generation logic
        # We call the internal generator directly to verify content
        # Inject order context into asset as done in fulfillment
        asset_dict = dict(asset)
        asset_dict['print_size'] = '18x24'
        asset_dict['layout_id'] = 'smart_v2_vertical_banner'
        
        # Generate
        pdf_key = _generate_smartsign_pdf(db, {'id': order_id, 'order_type': 'smart_sign', 'design_payload': json.dumps(payload)}, get_storage())
        
        assert pdf_key is not None
        assert "smart.pdf" in pdf_key
        
        # 5. Extract Text from PDF to verify rendering
        storage = get_storage()
        pdf_bytes = storage.get_file(pdf_key)
        
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        text = ""
        for page in doc:
            text += page.get_text()
            
        print("PDF Text:\n", text)
        
        assert "Persistence Agent" in text
        assert "555-9999" in text
        assert "TestLic:12345678" in text # Label + Number
