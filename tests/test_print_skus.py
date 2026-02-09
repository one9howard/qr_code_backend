import pytest
from services.print_catalog import validate_sku_strict, get_price_id, get_lookup_key
from services import stripe_price_resolver


@pytest.fixture(autouse=True)
def inject_price_cache():
    """Inject resolver cache so get_price_id works in APP_STAGE=test without Stripe network calls."""
    # Ensure test mode
    import os
    os.environ.setdefault('APP_STAGE', 'test')
    os.environ.setdefault('FLASK_ENV', 'test')

    # Build minimal cache for keys used in these tests
    mapping = {
        get_lookup_key('yard_sign', '18x24', 'coroplast_4mm'): 'price_mock_123',
        get_lookup_key('smart_sign', '18x24', 'aluminum_040'): 'price_mock_456',
        get_lookup_key('smart_riser', '6x24', 'aluminum_040'): 'price_mock_789',
    }
    stripe_price_resolver.clear_cache()
    stripe_price_resolver.set_cache(mapping)
    yield
    stripe_price_resolver.clear_cache()


def test_yard_sign_skus():
    ok, reason = validate_sku_strict('yard_sign', '18x24', 'coroplast_4mm')
    assert ok, f"Should be valid: {reason}"

    ok, reason = validate_sku_strict('yard_sign', '18x24', 'aluminum_040')
    assert ok, f"Should be valid: {reason}"

    ok, reason = validate_sku_strict('yard_sign', '18x24', 'cardboard')
    assert not ok
    assert reason == 'invalid_material'

    ok, reason = validate_sku_strict('yard_sign', '6x24', 'coroplast_4mm')
    assert not ok
    assert reason == 'invalid_size_for_material'


def test_smart_sign_skus():
    ok, reason = validate_sku_strict('smart_sign', '18x24', 'aluminum_040')
    assert ok, f"Should be valid: {reason}"

    ok, reason = validate_sku_strict('smart_sign', '18x24', 'coroplast_4mm')
    assert not ok
    assert reason == 'invalid_material'

    ok, reason = validate_sku_strict('smart_sign', '12x12', 'aluminum_040')
    assert not ok
    assert reason == 'invalid_size'


def test_smart_riser_skus():
    ok, reason = validate_sku_strict('smart_riser', '6x24', 'aluminum_040')
    assert ok, f"Should be valid: {reason}"

    ok, reason = validate_sku_strict('smart_riser', '6x36', 'aluminum_040')
    assert ok, f"Should be valid: {reason}"

    ok, reason = validate_sku_strict('smart_riser', '18x24', 'aluminum_040')
    assert not ok
    assert reason == 'invalid_size'


def test_get_price_id_uses_cache_in_test_mode():
    pid = get_price_id('yard_sign', '18x24', 'coroplast_4mm')
    assert pid == 'price_mock_123'
