import pytest
from unittest.mock import patch, MagicMock

@pytest.fixture
def setup_data(client, db):
    # Setup Users using the shared db connection
    pro_id = db.execute("INSERT INTO users (email, password_hash, subscription_status, is_verified) VALUES ('pro@example.com', 'hash', 'active', true) RETURNING id").fetchone()['id']
    free_id = db.execute("INSERT INTO users (email, password_hash, subscription_status, is_verified) VALUES ('free@example.com', 'hash', 'free', true) RETURNING id").fetchone()['id']
    
    # Setup Agent for Pro
    agent_id = db.execute("INSERT INTO agents (user_id, name, brokerage, email) VALUES (%s, 'Pro Agent', 'Test Realty', 'pro@example.com') RETURNING id", (pro_id,)).fetchone()['id']

    # Setup Property for Pro
    property_id = db.execute("INSERT INTO properties (agent_id, address, beds, baths) VALUES (%s, '123 Test St', '3', '2') RETURNING id", (agent_id,)).fetchone()['id']

    # Setup Asset for Pro
    asset_id = db.execute("INSERT INTO sign_assets (user_id, code, label) VALUES (%s, 'PRO123', 'My Sign') RETURNING id", (pro_id,)).fetchone()['id']
    
    db.commit()
    
    # Attach ids to client for convenience
    client.pro_id = pro_id
    client.free_id = free_id
    client.asset_id = asset_id
    client.property_id = property_id

def login(client, user_id):
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user_id)
        sess['_fresh'] = True

class TestSmartSignPrinting:

    def test_edit_access_control_free(self, client, setup_data):
        # 1. Free user cannot edit
        login(client, client.free_id)
        resp = client.get(f"/dashboard/sign-assets/{client.asset_id}/edit")
        assert resp.status_code == 403 or resp.status_code == 404

    def test_edit_access_control_pro(self, client, setup_data):
        # 2. Pro user (Owner) can edit
        login(client, client.pro_id)
        resp = client.get(f"/dashboard/sign-assets/{client.asset_id}/edit")
        assert resp.status_code == 200
        assert b"Edit SmartSign Design" in resp.data

    def test_edit_design(self, client, setup_data, db):
        login(client, client.pro_id)
        resp = client.post(f"/dashboard/sign-assets/{client.asset_id}/edit", data={
            'brand_name': 'New Brand',
            'cta_key': 'scan_for_details',
            'background_style': 'dark',
            'include_logo': 'on'
        }, follow_redirects=True)
        assert resp.status_code == 200
        
        asset = db.execute("SELECT * FROM sign_assets WHERE id=%s", (client.asset_id,)).fetchone()
        assert asset['brand_name'] == 'New Brand'
        assert asset['background_style'] == 'dark'
        assert asset['include_logo'] is True

    @patch('routes.smart_signs.stripe.checkout.Session.create')
    @patch('os.environ.get')
    def test_checkout_flow(self, mock_env, mock_stripe, client, setup_data, db):
        # Mock Price
        def get_env(key, default=None):
            if key == 'SMARTSIGN_PRICE_CENTS': return '2900'
            return default
        mock_env.side_effect = get_env
        
        mock_stripe.return_value = MagicMock(id='sess_123', url='http://stripe.url')
        
        login(client, client.pro_id)
        resp = client.post("/orders/smart-sign/checkout", data={
            'asset_id': client.asset_id,
            'property_id': client.property_id
        })
        
        assert resp.status_code == 303
        assert resp.location == 'http://stripe.url'
        
        # Verify Order Created
        order = db.execute("SELECT * FROM orders WHERE sign_asset_id=%s", (client.asset_id,)).fetchone()
        assert order is not None
        assert order['status'] == 'pending_payment'
        assert order['stripe_checkout_session_id'] == 'sess_123'

    @patch('routes.webhook.fulfill_order')
    def test_webhook_activation(self, mock_fulfill, client, setup_data, db):
        # 1. Create pending order
        order_id = db.execute("""
            INSERT INTO orders (user_id, sign_asset_id, property_id, status, order_type) 
            VALUES (%s, %s, %s, 'pending_payment', 'smart_sign') 
            RETURNING id
        """, (client.pro_id, client.asset_id, client.property_id)).fetchone()['id']
        db.commit()
        
        # 2. Simulate Webhook
        payload = {
            'id': 'evt_123',
            'type': 'checkout.session.completed',
            'data': {
                'object': {
                    'id': 'sess_fake',
                    'mode': 'payment',
                    'payment_status': 'paid',
                    'payment_intent': 'pi_fake',
                    'amount_total': 2900,
                    'currency': 'usd',
                    'metadata': {
                        'purpose': 'smart_sign',
                        'order_id': str(order_id),
                        'sign_asset_id': str(client.asset_id)
                    }
                }
            }
        }
        
        with patch('stripe.Webhook.construct_event') as mock_construct:
            mock_construct.return_value = payload
            resp = client.post("/stripe/webhook", json=payload, headers={'Stripe-Signature': 'fake'})
            assert resp.status_code == 200
            
        # 3. Verify Activation
        asset = db.execute("SELECT * FROM sign_assets WHERE id=%s", (client.asset_id,)).fetchone()
        assert asset['activated_at'] is not None
        assert asset['activation_order_id'] == order_id
        
        order = db.execute("SELECT * FROM orders WHERE id=%s", (order_id,)).fetchone()
        assert order['status'] == 'paid'
        
        # 4. Verify Fulfillment Triggered
        mock_fulfill.assert_called_with(str(order_id)) 

    @patch('services.fulfillment.generate_smartsign_pdf')
    def test_fulfillment_generation(self, mock_gen, client, setup_data, db):
        mock_gen.return_value = "pdfs/generated.pdf"
        
        # Setup paid order without PDF
        order_id = db.execute("""
            INSERT INTO orders (user_id, sign_asset_id, property_id, status, order_type, sign_pdf_path) 
            VALUES (%s, %s, %s, 'paid', 'smart_sign', NULL) 
            RETURNING id
        """, (client.pro_id, client.asset_id, client.property_id)).fetchone()['id']
        db.commit()
        
        db.commit()
        
        from services.fulfillment import fulfill_order
        
        # Run
        # Mock get_storage to return True for exists
        with patch('services.fulfillment_providers.internal.InternalQueueProvider.submit_order') as mock_submit, \
             patch('utils.storage.get_storage') as mock_storage_cls:
             
            mock_storage_instance = MagicMock()
            mock_storage_instance.exists.return_value = True
            mock_storage_cls.return_value = mock_storage_instance

            mock_submit.return_value = "job_123"
            success = fulfill_order(order_id)
            assert success is True
            
        # Verify PDF Gen called
        mock_gen.assert_called_once()
        
        # Verify Order updated
        order = db.execute("SELECT * FROM orders WHERE id=%s", (order_id,)).fetchone()
        assert order['sign_pdf_path'] == "pdfs/generated.pdf"
        assert order['status'] == 'submitted_to_printer'
