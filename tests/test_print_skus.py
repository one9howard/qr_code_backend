import pytest
from unittest.mock import MagicMock, patch
from services.print_catalog import validate_sku_strict, get_price_id

# Mock database
class MockDB:
    def execute(self, query, params=None):
        return MagicMock() # returns cursor

# We need to mock the stripe_price_resolver because get_price_id uses it
@pytest.fixture(autouse=True)
def mock_resolver():
    with patch('services.print_catalog.resolve_price_id', return_value='price_mock_123'):
        yield

def test_listing_sign_skus():
    # Valid
    # Coroplast + Double (Forced)
    ok, reason = validate_sku_strict('listing_sign', '18x24', 'coroplast_4mm')
    assert ok, f"Should be valid: {reason}"
    
    # Aluminum + Double
    ok, reason = validate_sku_strict('listing_sign', '18x24', 'aluminum_040')
    assert ok
    
    # Invalid Material
    ok, reason = validate_sku_strict('listing_sign', '18x24', 'cardboard')
    assert not ok
    assert reason == 'invalid_material'
    
    # Invalid Size for Coroplast (e.g. 6x24 is Riser only)
    ok, reason = validate_sku_strict('listing_sign', '6x24', 'coroplast_4mm')
    assert not ok
    assert reason == 'invalid_size'

def test_smart_sign_skus():
    # Valid: Aluminum, 18x24
    ok, reason = validate_sku_strict('smart_sign', '18x24', 'aluminum_040')
    assert ok
    
    # Invalid: Coroplast
    ok, reason = validate_sku_strict('smart_sign', '18x24', 'coroplast_4mm')
    assert not ok
    assert reason == 'invalid_material'
    
    # Invalid Size
    ok, reason = validate_sku_strict('smart_sign', '12x12', 'aluminum_040')
    # 12x12 not in list presumably
    assert not ok

def test_smart_riser_skus():
    # Valid
    ok, reason = validate_sku_strict('smart_riser', '6x24', 'aluminum_040')
    assert ok
    
    ok, reason = validate_sku_strict('smart_riser', '6x36', 'aluminum_040')
    assert ok
    
    # Invalid Size
    ok, reason = validate_sku_strict('smart_riser', '18x24', 'aluminum_040')
    assert not ok
    assert reason == 'invalid_size'

def test_get_price_id_uses_resolver():
    # Helper to check if get_price_id works and calls resolver
    pid = get_price_id('listing_sign', '18x24', 'coroplast_4mm')
    assert pid == 'price_mock_123'

def test_validates_pdf_generation_listing_sign():
    # Mock services.printing.listing_sign
    # We want to verify it produces valid PDF bytes (mocked)
    from services.printing.listing_sign import generate_listing_sign_pdf
    
    order = MagicMock()
    order.design_payload = {'agent_name': 'Test Agent'} 
    # Use real dict/object structure expected by updated function
    # The updated function in listing_sign.py accesses attributes `order.design_payload`
    # and `order.print_size`, etc.
    order.print_size = '18x24'
    order.sides = 'double'
    order.material = 'coroplast_4mm'
    
    # We must mock Property DB lookup inside generate_listing_sign_pdf 
    # OR we provide enough in order ?
    # The rewritten listing_sign.py does:
    # prop = Property.query.get(prop_id)
    # So we need to mock db queries.
    
    with patch('models.Property.query') as mock_prop_q:
        with patch('models.User.query') as mock_user_q:
            mock_prop = MagicMock()
            mock_prop.address = "123 Main"
            mock_prop_q.get.return_value = mock_prop
            
            mock_user = MagicMock()
            mock_user.first_name = "Agent"
            mock_user.last_name = "Smith"
            mock_user_q.get.return_value = mock_user
            
            # Also mock PDF canvas to avoid reportlab issues or file I/O?
            # Actually reportlab is fine in tests usually.
            # But we overwrote it to take (order, output_path) or (..., buffer)?
            # Wait, fulfillment calls `generate_listing_sign_pdf(order, output_path)`
            # My `listing_sign.py` overwrite: `generate_listing_sign_pdf(db, order)` ???
            
            # Let's check `listing_sign.py` signature in my previous overwrite.
            # I wrote: `def generate_listing_sign_pdf(db, order):` (Line 20)
            # But fulfillment calls: `pdf_bytes = generate_listing_sign_pdf(db, order_map)`
            # Wait, fulfillment overwrite says:
            # `from services.printing.listing_sign import generate_listing_sign_pdf`
            # `pdf_bytes = generate_listing_sign_pdf(db, order_map)`
            
            # So the SIGNATURE is `(db, order)`.
            
            # But wait, looking at my `listing_sign.py` overwrite content:
            # It returns `buffer.read()` -> bytes.
            # Implementation: `prop = db.execute(...).fetchone()`
            # It uses `db` directly, NOT models.Property.query.
            
            # My test mock above sets up Property.query. 
            # I must check if `listing_sign.py` uses direct SQL now.
            # Checking overwrite...
            # `prop = db.execute("SELECT * FROM properties...").fetchone()`
            # Yes, direct SQL.
            
            mock_db = MagicMock()
            mock_db.execute.return_value.fetchone.side_effect = [
                {'address': '123 Main', 'beds': '3', 'baths': '2', 'price': '$500k'}, # Property
                {'name': 'Agent Smith', 'email': 'a@b.com'} # User
            ]
            
            try:
                # Passing order dict since it expects order.get or order['keys']
                # The code: `order.get('design_payload')` -> implies dict.
                # `order.get('property_id')`
                
                order_dict = {
                     'property_id': 1,
                     'user_id': 2,
                     'design_payload': {},
                     'print_size': '18x24',
                     'sides': 'double'
                }
                
                res = generate_listing_sign_pdf(mock_db, order_dict)
                assert res.startswith(b'%PDF'), "Result should be PDF bytes"
                
            except Exception as e:
                pytest.fail(f"PDF Gen failed: {e}")

