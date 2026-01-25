
import pytest
from app import create_app
from database import get_db

@pytest.fixture
def app():
    app = create_app()
    app.config.update({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False
    })
    return app

@pytest.fixture
def client(app):
    return app.test_client()

def test_guest_linking_security(client, app):
    """
    Test that registration only links orders if guest_token matches.
    """
    with app.app_context():
        db = get_db()
        # 1. Create a guest order with a specific token
        victim_email = "victim@example.com"
        attacker_email = "victim@example.com" # Attacker registers as victim
        guest_token = "secure_token_123"
        
        db.execute(
            "INSERT INTO orders (request_id, guest_email, guest_token, status, order_type) VALUES (%s, %s, %s, 'pending', 'sign')",
            ("req_victim", victim_email, guest_token)
        )
        db.commit()
        
        # 2. Attacker registers with NO guest_token in session
        # Should NOT link order
        res = client.post("/auth/register", data={
            "full_name": "Attacker",
            "email": attacker_email,
            "password": "password123",
            "brokerage": "BadGuys",
            "phone": "555-0000"
        }, follow_redirects=True)
        assert res.status_code == 200
        
        user = db.execute("SELECT id FROM users WHERE email = %s", (attacker_email,)).fetchone()
        assert user is not None
        user_id = user['id']
        
        # Check order ownership
        order = db.execute("SELECT user_id FROM orders WHERE request_id = 'req_victim'").fetchone()
        # Should still be NULL
        assert order['user_id'] is None, "Order was linked without guest_token!"
        
        # 3. Legitimate user logs in WITH guest_token
        with client.session_transaction() as sess:
            sess['guest_token'] = guest_token
            
        res = client.post("/auth/login", data={
            "email": attacker_email,
            "password": "password123"
        }, follow_redirects=True)
        
        # Check order ownership again
        order = db.execute("SELECT user_id FROM orders WHERE request_id = 'req_victim'").fetchone()
        assert order['user_id'] == user_id, "Order should have been linked with matching token"

    def test_guest_tokens_list_linking(self, client, app):
         """Test linking when using the list of tokens (multiple queued orders)."""
         with app.app_context():
            db = get_db()
            email = "unverifiedLIST@example.com"
            token1 = "mk_1"
            token2 = "mk_2"
            
            # Create two orders with different tokens
            db.execute("INSERT INTO orders (request_id, guest_email, guest_token, status, order_type) VALUES (%s, %s, %s, 'pending', 'sign')",
                       ("req_1", email, token1))
            db.execute("INSERT INTO orders (request_id, guest_email, guest_token, status, order_type) VALUES (%s, %s, %s, 'pending', 'sign')",
                       ("req_2", email, token2))
            db.commit()
            
            # User registers with BOTH tokens in session
            with client.session_transaction() as sess:
                sess['guest_tokens'] = [token1, token2]
                
            res = client.post("/auth/register", data={
                "full_name": "Multi User",
                "email": email,
                "password": "password",
                "brokerage": "B",
                "phone": "1"
            }, follow_redirects=True)
            
            user = db.execute("SELECT id FROM users WHERE email=%s", (email,)).fetchone()
            uid = user['id']
            
            o1 = db.execute("SELECT user_id FROM orders WHERE request_id='req_1'").fetchone()
            o2 = db.execute("SELECT user_id FROM orders WHERE request_id='req_2'").fetchone()
            
            assert o1['user_id'] == uid
            assert o2['user_id'] == uid

