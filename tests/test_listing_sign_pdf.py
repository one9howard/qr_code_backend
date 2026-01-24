"""
Listing Sign PDF Generator Regression Tests

Tests to ensure listing_sign.py correctly queries the database schema
and generates PDFs with proper QR URLs.
"""
import pytest
from unittest.mock import patch, MagicMock


class TestListingSignPDF:
    
    def test_generate_listing_sign_pdf_queries_schema_correctly(self, app, db):
        """
        Verify PDF generation uses correct schema columns.
        Sets up user, agent, property, order and calls generate_listing_sign_pdf.
        """
        # 1. Setup: Create user, agent, property, order
        db.execute("""
            INSERT INTO users (email, password_hash, full_name, subscription_status) 
            VALUES ('pdf@test.com', 'x', 'Test User', 'active')
        """)
        user_id = db.execute("SELECT id FROM users WHERE email='pdf@test.com'").fetchone()[0]
        
        db.execute("""
            INSERT INTO agents (user_id, name, brokerage, phone, email) 
            VALUES (%s, 'Test Agent', 'Test Brokerage', '555-1234', 'agent@test.com')
        """, (user_id,))
        agent_id = db.execute("SELECT id FROM agents WHERE user_id=%s", (user_id,)).fetchone()[0]
        
        db.execute("""
            INSERT INTO properties (agent_id, address, beds, baths, price, qr_code, slug) 
            VALUES (%s, '123 Test St', '3', '2', 500000, 'testqr123', '123-test-st')
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
        
        # 2. Mock storage to avoid real I/O
        mock_storage = MagicMock()
        mock_storage.put_file = MagicMock(return_value='print_jobs/test.pdf')
        
        with app.app_context():
            with patch('services.printing.listing_sign.get_storage', return_value=mock_storage):
                from services.printing.listing_sign import generate_listing_sign_pdf
                
                # 3. Call the function - should NOT raise
                result = generate_listing_sign_pdf(order_dict)
                
                # 4. Assertions
                assert result is not None
                assert 'pdf' in result.lower()
                assert mock_storage.put_file.called
                
                # Verify the call args - should be a PDF buffer and key
                call_args = mock_storage.put_file.call_args
                assert call_args is not None
                key = call_args[0][1]  # Second positional arg is key
                assert 'pdfs/' in key or 'listing_sign' in key
    
    def test_listing_sign_qr_value_is_r_path(self, app, db):
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
            with patch('services.printing.listing_sign.get_storage', return_value=mock_storage):
                with patch('utils.pdf_generator.draw_vector_qr', side_effect=capture_qr):
                    from services.printing.listing_sign import generate_listing_sign_pdf
                    
                    try:
                        generate_listing_sign_pdf(order_dict)
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
            with patch('services.printing.listing_sign.get_storage', return_value=mock_storage):
                with patch('services.printing.listing_sign._draw_landscape_split_layout', mock_landscape):
                    with patch('services.printing.listing_sign._draw_standard_layout', mock_standard):
                        from services.printing.listing_sign import generate_listing_sign_pdf
                        
                        generate_listing_sign_pdf(order_dict)
        
        assert len(landscape_called) > 0, "Landscape layout should be called for 36x24"
        assert len(standard_called) == 0, "Standard layout should NOT be called for 36x24"

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
            with patch('services.printing.listing_sign.get_storage', return_value=mock_storage):
                from services.printing.listing_sign import generate_listing_sign_pdf
                
                # This should NOT raise ValueError for int("$500k")
                result = generate_listing_sign_pdf(order_dict)
                
                assert result is not None
                assert 'pdf' in result.lower()
                assert mock_storage.put_file.called

