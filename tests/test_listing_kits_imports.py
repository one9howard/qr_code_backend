
from unittest.mock import patch, MagicMock
import pytest

def test_listing_kits_import():
    """Ensure routes and services can be imported without error."""
    import routes.listing_kits
    import services.listing_kits
    assert True

def test_kit_zip_builder_structure():
    """Test kit generation zip structure using mocks."""
    from services.listing_kits import generate_kit
    
    with patch('services.listing_kits.get_db') as mock_get_db, \
         patch('services.listing_kits.get_storage') as mock_get_storage, \
         patch('services.listing_kits.generate_pdf_sign') as mock_gen_pdf:
         
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        
        # Mock Data
        mock_db.execute.side_effect = [
            MagicMock(fetchone=lambda: {'id': 1, 'property_id': 101}), # Kit
            MagicMock(fetchone=lambda: { # Property
                'id': 101, 'address': '123 Main', 'beds': 3, 'baths': 2, 'sqft': 2000, 'price': 500000,
                'agent_name': 'Agent', 'brokerage': 'Broker', 'agent_email': 'e@mail.com', 'agent_phone': '555-1212',
                'qr_code': 'ABC', 'slug': 'slug', 'user_id': 1, 'photo_filename': None, 'logo_filename': None
            }),
            MagicMock(fetchone=lambda: None) # No existing order
        ]
        
        # Mock PDF Gen return
        mock_gen_pdf.return_value = "temp/key.pdf"
        
        # Mock Storage
        mock_storage = MagicMock()
        mock_get_storage.return_value = mock_storage
        
        # Run
        generate_kit(1)
        
        # Assertions
        mock_gen_pdf.assert_called()
        # Verify Zip upload
        zip_call = next((c for c in mock_storage.put_file.call_args_list if c[0][1].endswith('.zip')), None)
        assert zip_call
