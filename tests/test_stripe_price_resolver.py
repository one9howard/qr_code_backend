import pytest
import time
from unittest.mock import MagicMock, patch
from services import stripe_price_resolver
from services.stripe_price_resolver import resolve_price_id, warm_cache, LookupKeyMissingError, DuplicateActivePriceError, InactiveProductError

# Ensure ANY stripe call is blocked in these tests unless patched
@pytest.fixture(autouse=True)
def block_stripe():
    with patch('stripe.Price.list', side_effect=RuntimeError("NETWORK CALL")):
        yield

def test_resolve_price_id_returns_mock_in_test_mode(block_stripe):
    """
    Confirms that resolve_price_id returns a mock price ID in test mode
    when no cache is set and no valid Stripe key is available.
    """
    with patch.dict('os.environ', {'APP_STAGE': 'test'}):
        result = resolve_price_id("missing_key")
        assert result == "price_mock_missing_key"

def test_resolve_uses_injected_cache():
    """
    Verifies test helper set_cache works and resolve_price_id reads it.
    """
    with patch.dict('os.environ', {'APP_STAGE': 'test'}):
        stripe_price_resolver.set_cache({'test_key': 'price_123'})
        assert resolve_price_id('test_key') == 'price_123'

def test_warm_cache_forbidden_in_test():
    """
    warm_cache should Raise in test mode if called (because it calls network).
    """
    with patch.dict('os.environ', {'APP_STAGE': 'test'}):
        with pytest.raises(RuntimeError, match="warm_cache called in TEST mode"):
            warm_cache(['k1'])

# --- MOCK LOGIC TESTS (Bypassing Test Guards to test the Logic itself) ---
# To test the logic (batching, strictness), we temporarily pretend we are NOT in test mode
# OR we mock the module internals to bypass the guard, but mocking the stripe call is cleaner.

@patch.dict('os.environ', {'APP_STAGE': 'prod'}) # Pretend prod to run logic
@patch('stripe.Price.list')
def test_warm_cache_success(mock_list):
    """
    Verify warm_cache fetches, validates, and populates cache.
    """
    # clear cache
    stripe_price_resolver.clear_cache()
    
    # Mock Response
    # Key1: OK
    # Key2: OK
    mock_price1 = MagicMock()
    mock_price1.id = "price_A"
    mock_price1.lookup_key = "key_A"
    mock_price1.product.active = True
    
    mock_price2 = MagicMock()
    mock_price2.id = "price_B"
    mock_price2.lookup_key = "key_B"
    mock_price2.product.active = True
    
    mock_list.return_value.data = [mock_price1, mock_price2]
    
    warm_cache(['key_A', 'key_B'])
    
    assert resolve_price_id('key_A') == 'price_A'
    assert resolve_price_id('key_B') == 'price_B'
    
    # Verify batching args
    mock_list.assert_called_with(lookup_keys=['key_A', 'key_B'], active=True, limit=100, expand=['data.product'])


@patch.dict('os.environ', {'APP_STAGE': 'prod'})
@patch('stripe.Price.list')
def test_validation_inactive_product(mock_list):
    stripe_price_resolver.clear_cache()
    
    p = MagicMock()
    p.lookup_key = "key_bad"
    p.id = "price_bad"
    p.product.active = False # INACTIVE
    
    mock_list.return_value.data = [p]
    
    with pytest.raises(InactiveProductError):
        warm_cache(['key_bad'])

@patch.dict('os.environ', {'APP_STAGE': 'prod'})
@patch('stripe.Price.list')
def test_validation_duplicate_prices(mock_list):
    stripe_price_resolver.clear_cache()
    
    p1 = MagicMock()
    p1.lookup_key = "dup"
    p1.id = "p1"
    
    p2 = MagicMock()
    p2.lookup_key = "dup"
    p2.id = "p2"
    
    mock_list.return_value.data = [p1, p2]
    
    with pytest.raises(DuplicateActivePriceError):
        warm_cache(['dup'])

@patch.dict('os.environ', {'APP_STAGE': 'prod'})
@patch('stripe.Price.list')
def test_validation_missing_key(mock_list):
    stripe_price_resolver.clear_cache()
    mock_list.return_value.data = [] # Empty
    
    with pytest.raises(LookupKeyMissingError):
        warm_cache(['ghost_key'])
