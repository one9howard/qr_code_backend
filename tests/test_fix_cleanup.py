
from routes.webhook import handle_payment_checkout

def test_smart_riser_webhook_behavior(app, mocker):
    """
    Regression Test: SmartRiser checkout (order_type='sign') 
    should NOT trigger SmartSign activation in webhook.
    """
    # Mock DB
    mock_db = mocker.Mock()
    # Mock row return for order lookup
    # Return status='paid', order_type='sign' (simulating what SmartRiser now inserts)
    mock_db.execute.return_value.fetchone.return_value = {
        'status': 'pending_payment', 
        'order_type': 'sign', 
        'property_id': None,
        'user_id': 1
    }
    
    # Mock event/session
    session = {
        'id': 'sess_123',
        'metadata': {
            'order_id': '100',
            'order_type': 'sign', # This is KEY: SmartRiser now sends 'sign'
            'user_id': '1'
        },
        'payment_status': 'paid'
    }
    
    # If called, this should fail the test immediately.
    mock_generate_code = mocker.patch(
        'routes.webhook.generate_unique_code',
        side_effect=Exception("Should not be called!")
    )
    mock_process_paid_order = mocker.patch('services.orders.process_paid_order')

    handle_payment_checkout(mock_db, session)

    mock_process_paid_order.assert_called_once_with(mock_db, session)
    assert not mock_generate_code.called, "SmartSign activation path should not run for order_type='sign'"
