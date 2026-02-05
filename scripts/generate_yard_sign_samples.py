
import sys
import os
import unittest.mock
from unittest.mock import MagicMock

# Add project root to path
sys.path.append(os.getcwd())

from services.printing.yard_sign import generate_yard_sign_pdf

# Mock DB
mock_db = MagicMock()
mock_conn = MagicMock()
mock_cursor = MagicMock()

@unittest.mock.patch('services.printing.yard_sign.get_db')
@unittest.mock.patch('services.printing.yard_sign.get_storage')
def run_test(mock_get_storage, mock_get_db):
    mock_get_db.return_value = mock_conn
    mock_storage = MagicMock()
    mock_get_storage.return_value = mock_storage
    mock_storage.exists.return_value = False 

    # Mock Data
    prop_row = {
        'id': 101, 'agent_id': 202,
        'address': '123 Premium Blvd',
        'city': 'Beverly Hills', 'state': 'CA', 'zip': '90210',
        'beds': 4, 'baths': 3.5, 'sqft': '3,500',
        'price': 1250000,
        'qr_code': 'ABC1234'
    }
    
    agent_row = {
        'id': 202,
        'agent_name': 'Victoria Sterling',
        'full_name': 'Victoria Sterling',
        'brokerage': 'Luxury Estates',
        'phone': '555-0199',
        'agent_email': 'victoria@example.com',
        'user_email': 'victoria@example.com'
    }
    
    user_row = {'full_name': 'Owner', 'email': 'owner@example.com'}

    def side_effect_execute(query, params):
        q = query.strip().upper()
        m = MagicMock()
        if "FROM PROPERTIES" in q:
            m.fetchone.return_value = prop_row
        elif "FROM AGENTS" in q:
            m.fetchone.return_value = agent_row
        elif "FROM USERS" in q:
            m.fetchone.return_value = user_row
        else:
            m.fetchone.return_value = None
        return m

    mock_conn.execute.side_effect = side_effect_execute
    mock_storage.put_file = MagicMock()

    # Layouts to test
    # (Checking listing_ variants as they are currently used in yard_sign.py)
    layouts = [
        'listing_standard',
        'listing_v2_phone_qr_premium',
        'listing_v2_address_qr_premium'
    ]
    
    sizes = ['18x24', '36x24']
    
    output_dir = "pdfs/samples_yard"
    os.makedirs(output_dir, exist_ok=True)
    
    print("Generating Yard Sign Samples...")
    
    for layout_id in layouts:
        for size in sizes:
            # Create Order Object (dict)
            order = {
                'id': 999,
                'property_id': 101,
                'user_id': 505,
                'sign_color': '#0f172a',
                'print_size': size,
                'layout_id': layout_id
            }
            
            try:
                generate_yard_sign_pdf(order)
                
                # Retrieve buffer from mock call
                if mock_storage.put_file.call_count > 0:
                    args, _ = mock_storage.put_file.call_args
                    pdf_bytes = args[0].getvalue()
                    
                    print(f"[OK] {layout_id} ({size}) - {len(pdf_bytes)} bytes")
                    
                    # Save to disk
                    fname = f"sample_{layout_id}_{size}.pdf"
                    with open(os.path.join(output_dir, fname), 'wb') as f:
                        f.write(pdf_bytes)
                    
                    # Reset
                    mock_storage.put_file.reset_mock()
                else:
                    print(f"[FAIL] {layout_id} ({size}): No Put File Call")
                    
            except Exception as e:
                print(f"[FAIL] {layout_id} ({size}): {e}")
                import traceback
                traceback.print_exc()

if __name__ == "__main__":
    run_test()
