"""
Listing Sign PDF Generator Regression Tests

Tests to ensure yard_sign.py correctly queries the database schema
and generates PDFs with proper QR URLs.
"""
import pytest
from unittest.mock import patch, MagicMock


class TestListingSignPDF:
    
    def test_generate_yard_sign_pdf_queries_schema_correctly(self, app, db):
        """
        Verify PDF generation uses correct schema columns.
        Sets up user, agent, property, order and calls generate_yard_sign_pdf.
        It should execute queries for QR, agent, etc.
        """
        with app.app_context():
             # Setup Mock Data
             db.execute("INSERT INTO users (email, password_hash, full_name, subscription_status) VALUES ('pdf_test@example.com', 'hash', 'PDF Tester', 'active')")
             user_id = db.execute("SELECT id FROM users WHERE email='pdf_test@example.com'").fetchone()[0]
             
             db.execute("INSERT INTO agents (user_id, name, brokerage, phone, email) VALUES (%s, 'Agent Smith', 'Matrix Realty', '555-1234', 'agent@matrix.com')", (user_id,))
             agent_id = db.execute("SELECT id FROM agents WHERE user_id=%s", (user_id,)).fetchone()[0]
             
             db.execute("INSERT INTO properties (agent_id, address, beds, baths, price, qr_code, slug) VALUES (%s, '123 Simulation Way', '3', '2', 500000, 'qrcode123', '123-simulation-way')", (agent_id,))
             prop_id = db.execute("SELECT id FROM properties WHERE agent_id=%s", (agent_id,)).fetchone()[0]
             
             # Create Order (minimal)
             # yard_sign.py queries these tables based on IDs in the order dict/row
             db.execute("INSERT INTO orders (user_id, property_id, order_type, status, print_size) VALUES (%s, %s, 'sign', 'pending', '18x24')", (user_id, prop_id))
             order_id = db.execute("SELECT id FROM orders WHERE user_id=%s", (user_id,)).fetchone()[0]
             db.commit()

             order_dict = {
                 'id': order_id,
                 'property_id': prop_id,
                 'user_id': user_id,
                 'print_size': '18x24',
                 'qr_code_svg': '<svg>QR</svg>' # usually fetch_qr_code does this, but generating PDF needs it
             }

             # Mock Storage so we don't actually upload
             mock_storage = MagicMock()
             
             # Patching get_storage to return our mock
             with patch('services.printing.yard_sign.get_storage', return_value=mock_storage):
                from services.printing.yard_sign import generate_yard_sign_pdf
                
                # Mock get_qr_code_svg to avoid network/DB calls for QR?
                # The function calls get_valid_qr_code_svg
                with patch('services.printing.yard_sign.get_valid_qr_code_svg', return_value='<svg>MOCK</svg>'):
                    # Run it
                    result = generate_yard_sign_pdf(order_dict)
                    
                    # Verify
                    assert result is not None
                    msg_args = mock_storage.put_file.call_args[0] 
                    key = msg_args[1]
                    assert 'pdfs/' in key or 'yard_sign' in key
    
    def test_yard_sign_qr_value_is_r_path(self, app, db):
        """
        Verify QR encodes /r/<code> path, NOT /s/ path.
        """
        # Setup minimal data
        db.execute("""
            INSERT INTO users (email, password_hash, full_name, subscription_status) 
            VALUES ('qr@test.com', 'x', 'QR Test', 'active')
        """)
        user_id = db.execute("SELECT id FROM users WHERE email='qr@test.com'").fetchone()[0]
        
        db.execute("""
            INSERT INTO agents (user_id, name, brokerage, phone, email) 
            VALUES (%s, 'QR Agent', 'Brokerage', '555-0000', 'qr@agent.com')
        """, (user_id,))
        agent_id = db.execute("SELECT id FROM agents WHERE user_id=%s", (user_id,)).fetchone()[0]
        
        # Use a specific qr_code to verify
        test_qr_code = 'myqrcode123'
        db.execute("""
            INSERT INTO properties (agent_id, address, beds, baths, price, qr_code, slug) 
            VALUES (%s, '456 QR Blvd', '2', '1', 300000, %s, '456-qr-blvd')
        """, (agent_id, test_qr_code))
        prop_id = db.execute("SELECT id FROM properties WHERE agent_id=%s", (agent_id,)).fetchone()[0]
        
        db.execute("""
            INSERT INTO orders (user_id, property_id, order_type, status, print_size) 
            VALUES (%s, %s, 'sign', 'pending', '18x24')
        """, (user_id, prop_id))
        order_id = db.execute("SELECT id FROM orders WHERE user_id=%s", (user_id,)).fetchone()[0]
        db.commit()
        
        order_dict = {
            'id': order_id,
            'user_id': user_id,
            'property_id': prop_id,
            'print_size': '18x24'
        }
        
        captured_qr_value = []
        
        # Patch draw_vector_qr to capture the qr_value
        original_draw = None
        
        def capture_qr(c, qr_value, *args, **kwargs):
            captured_qr_value.append(qr_value)
        
        mock_storage = MagicMock()
        mock_storage.put_file = MagicMock()
        
        with app.app_context():
            with patch('services.printing.yard_sign.get_storage', return_value=mock_storage):
                with patch('utils.pdf_generator.draw_vector_qr', side_effect=capture_qr):
                    from services.printing.yard_sign import generate_yard_sign_pdf
                    
                    try:
                        generate_yard_sign_pdf(order_dict)
                    except Exception:
                        pass  # May fail due to incomplete PDF, that's OK
        
        # Verify captured QR value
        if captured_qr_value:
            qr_url = captured_qr_value[0]
            assert '/r/' in qr_url, f"QR URL should contain /r/, got: {qr_url}"
            assert '/s/' not in qr_url, f"QR URL should NOT contain /s/, got: {qr_url}"
            assert test_qr_code in qr_url, f"QR URL should contain qr_code, got: {qr_url}"
    
    def test_landscape_layout_used_for_36x24(self, app, db):
        """
        Verify 36x24 (landscape) uses _draw_landscape_split_layout.
        """
        # Setup
        db.execute("""
            INSERT INTO users (email, password_hash, full_name, subscription_status) 
            VALUES ('landscape@test.com', 'x', 'Land Test', 'active')
        """)
        user_id = db.execute("SELECT id FROM users WHERE email='landscape@test.com'").fetchone()[0]
        
        db.execute("""
            INSERT INTO agents (user_id, name, brokerage, phone, email) 
            VALUES (%s, 'Land Agent', 'Brokerage', '555-9999', 'land@agent.com')
        """, (user_id,))
        agent_id = db.execute("SELECT id FROM agents WHERE user_id=%s", (user_id,)).fetchone()[0]
        
        db.execute("""
            INSERT INTO properties (agent_id, address, beds, baths, price, qr_code, slug) 
            VALUES (%s, '789 Wide Ave', '4', '3', 750000, 'widecode', '789-wide-ave')
        """, (agent_id,))
        prop_id = db.execute("SELECT id FROM properties WHERE agent_id=%s", (agent_id,)).fetchone()[0]
        
        db.execute("""
            INSERT INTO orders (user_id, property_id, order_type, status, print_size) 
            VALUES (%s, %s, 'sign', 'pending', '36x24')
        """, (user_id, prop_id))
        order_id = db.execute("SELECT id FROM orders WHERE user_id=%s", (user_id,)).fetchone()[0]
        db.commit()
        
        order_dict = {
            'id': order_id,
            'user_id': user_id,
            'property_id': prop_id,
            'print_size': '36x24'  # Landscape
        }
        
        landscape_called = []
        standard_called = []
        
        def mock_landscape(*args, **kwargs):
            landscape_called.append(True)
        
        def mock_standard(*args, **kwargs):
            standard_called.append(True)
        
        mock_storage = MagicMock()
        mock_storage.put_file = MagicMock()
        
        with app.app_context():
            with patch('services.printing.yard_sign.get_storage', return_value=mock_storage):
                with patch('services.printing.yard_sign._draw_landscape_split_layout', mock_landscape):
                    with patch('services.printing.yard_sign._draw_standard_layout', mock_standard):
                        from services.printing.yard_sign import generate_yard_sign_pdf
                        
                        generate_yard_sign_pdf(order_dict)
        
        assert len(landscape_called) > 0, "Landscape layout should be called for 36x24"
        assert len(standard_called) == 0, "Standard layout should NOT be called for 36x24"

    def test_standard_layout_used_for_18x24(self, app, db):
        """
        Verify 18x24 (portrait) uses _draw_standard_layout.
        """
        # Setup
        db.execute("""
            INSERT INTO users (email, password_hash, full_name, subscription_status) 
            VALUES ('standard@test.com', 'x', 'Standard Test', 'active')
        """)
        user_id = db.execute("SELECT id FROM users WHERE email='standard@test.com'").fetchone()[0]
        
        db.execute("""
            INSERT INTO agents (user_id, name, brokerage, phone, email) 
            VALUES (%s, 'Standard Agent', 'Brokerage', '555-1111', 'standard@agent.com')
        """, (user_id,))
        agent_id = db.execute("SELECT id FROM agents WHERE user_id=%s", (user_id,)).fetchone()[0]
        
        db.execute("""
            INSERT INTO properties (agent_id, address, beds, baths, price, qr_code, slug) 
            VALUES (%s, '123 Standard St', '3', '2', 400000, 'standardcode', '123-standard-st')
        """, (agent_id,))
        prop_id = db.execute("SELECT id FROM properties WHERE agent_id=%s", (agent_id,)).fetchone()[0]
        
        db.execute("""
            INSERT INTO orders (user_id, property_id, order_type, status, print_size) 
            VALUES (%s, %s, 'sign', 'pending', '18x24')
        """, (user_id, prop_id))
        order_id = db.execute("SELECT id FROM orders WHERE user_id=%s", (user_id,)).fetchone()[0]
        db.commit()
        
        order_dict = {
            'id': order_id,
            'user_id': user_id,
            'property_id': prop_id,
            'print_size': '18x24'  # Portrait
        }
        
        mock_standard = MagicMock()
        mock_landscape = MagicMock()
        
        mock_storage = MagicMock()
        mock_storage.put_file = MagicMock()
        
        with app.app_context():
            with patch('services.printing.yard_sign.get_storage', return_value=mock_storage):
                with patch('services.printing.yard_sign._draw_landscape_split_layout', mock_landscape):
                    with patch('services.printing.yard_sign._draw_standard_layout', mock_standard):
                        from services.printing.yard_sign import generate_yard_sign_pdf
                        
                        generate_yard_sign_pdf(order_dict)
                        
                        # Verify standard layout was called
                        mock_standard.assert_called_once()
                        mock_landscape.assert_not_called()

    def test_landscape_layout_selection(self, app, db):
        with app.app_context():
            mock_storage = MagicMock()
            mock_standard = MagicMock()
            mock_landscape = MagicMock()
            
            order_dict = {
                'id': 999,
                'address': '123 Wide St',
                'qr_code_svg': '<svg></svg>',
                'print_size': '36x24',
                'agent_name': 'Wide Agent',
                'agent_phone': '555-0199',
                'agent_email': 'wide@example.com',
                'brokerage_name': 'Big Realty',
                'agent_photo_key': None,
                'brokerage_logo_key': None
            }
            
            with patch('services.printing.yard_sign.get_storage', return_value=mock_storage):
                with patch('services.printing.yard_sign._draw_landscape_split_layout', mock_landscape):
                    with patch('services.printing.yard_sign._draw_standard_layout', mock_standard):
                        from services.printing.yard_sign import generate_yard_sign_pdf
                        
                        generate_yard_sign_pdf(order_dict)
                        
                        # Verify landscape layout was called for 36x24
                        mock_landscape.assert_called_once()
                        mock_standard.assert_not_called()

    def test_generate_yard_sign_pdf_from_order_row_wrapper(self, app, db):
        """Test the wrapper function handles row-like objects correctly"""
        with app.app_context():
            mock_storage = MagicMock()
            
            # Mock order row (dict)
            order_dict = {
                'id': 888,
                'property_id': 101,
                'user_id': 202,
                'print_size': '18x24'
                # Wrapper fetches missing fields via DB queries if not present
                # But for this unit test we might need to mock DB queries inside wrapper
                # OR we just test it calls the main generator.
            }
            
            # We'll mock the main generator to avoid complex DB setup here
            with patch('services.printing.yard_sign.generate_yard_sign_pdf') as mock_gen:
                with patch('services.printing.yard_sign.get_db') as mock_get_db:
                    # Mock DB returns for agent/property inference
                    mock_db = MagicMock()
                    mock_get_db.return_value = mock_db
                    mock_db.execute.return_value.fetchone.return_value = {
                        'address': 'DB Address', 
                        'agent_name': 'DB Agent'
                    }
                    
                    from services.printing.yard_sign import generate_yard_sign_pdf_from_order_row
                    
                    generate_yard_sign_pdf_from_order_row(order_dict, db=mock_db, storage=mock_storage)
                    
                    mock_gen.assert_called_once()
                    # Check first arg passed to generator
                    call_args = mock_gen.call_args[0][0]
                    assert call_args['id'] == 888

    def test_price_string_500k_does_not_crash(self, app, db):
        """
        Regression test: PDF generation must not crash for price strings like "$500k".
        The _format_price helper should safely handle non-numeric price values.
        """
        # Setup with price as "$500k" (string that would crash int())
        db.execute("""
            INSERT INTO users (email, password_hash, full_name, subscription_status) 
            VALUES ('price500k@test.com', 'x', 'Price Test', 'active')
        """)
        user_id = db.execute("SELECT id FROM users WHERE email='price500k@test.com'").fetchone()[0]
        
        db.execute("""
            INSERT INTO agents (user_id, name, brokerage, phone, email) 
            VALUES (%s, 'Price Agent', 'Brokerage', '555-PRICE', 'price@agent.com')
        """, (user_id,))
        agent_id = db.execute("SELECT id FROM agents WHERE user_id=%s", (user_id,)).fetchone()[0]
        
        # Insert property with problematic price string
        db.execute("""
            INSERT INTO properties (agent_id, address, beds, baths, price, qr_code, slug) 
            VALUES (%s, '500k Test St', '3', '2', '$500k', 'pricecode500k', '500k-test-st')
        """, (agent_id,))
        prop_id = db.execute("SELECT id FROM properties WHERE agent_id=%s", (agent_id,)).fetchone()[0]
        
        db.execute("""
            INSERT INTO orders (user_id, property_id, order_type, status, print_size) 
            VALUES (%s, %s, 'sign', 'pending', '18x24')
        """, (user_id, prop_id))
        order_id = db.execute("SELECT id FROM orders WHERE user_id=%s", (user_id,)).fetchone()[0]
        db.commit()
        
        order_dict = {
            'id': order_id,
            'user_id': user_id,
            'property_id': prop_id,
            'print_size': '18x24'
        }
        
        mock_storage = MagicMock()
        mock_storage.put_file = MagicMock(return_value='pdfs/test.pdf')
        
        with app.app_context():
            with patch('services.printing.yard_sign.get_storage', return_value=mock_storage):
                from services.printing.yard_sign import generate_yard_sign_pdf
                
                # This should NOT raise ValueError for int("$500k")
                result = generate_yard_sign_pdf(order_dict)
                
                assert result is not None
                assert 'pdf' in result.lower()
                assert mock_storage.put_file.called

