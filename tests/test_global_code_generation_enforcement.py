
import pytest
import secrets
from unittest.mock import patch, Mock
import contextlib

@pytest.fixture
def auth_client_with_property(client, db):
    # Setup user and property
    from werkzeug.security import generate_password_hash
    hashed_pw = generate_password_hash('password')
    user_id = db.execute(
        "INSERT INTO users (email, password_hash, is_verified, subscription_status) VALUES (%s, %s, %s, 'active') RETURNING id",
        ('qr@example.com', hashed_pw, True)
    ).fetchone()['id']
    
    agent_id = db.execute(
        "INSERT INTO agents (user_id, name, brokerage, email, phone) VALUES (%s, 'QR Agent', 'Brok', 'qr@example.com', '555-1234') RETURNING id", 
        (user_id,)
    ).fetchone()['id']
    
    db.commit()
    
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user_id)
        sess['_fresh'] = True
    
    return {
        'user_id': user_id,
        'agent_id': agent_id,
        'client': client
    }

def test_property_creation_uses_global_generator(auth_client_with_property, db):
    """
    MANDATORY: Assert that property creation calls utils.qr_codes.generate_unique_code 
    and DOES NOT use secrets.token_urlsafe directly for the qr_code.
    """
    client = auth_client_with_property['client']
    
    # We want to trap any call to secrets.token_urlsafe(9) or similar in the route handler.
    # However, flask-login or other internals might use secrets.token_urlsafe.
    # So we patch it to inspect WHO called it, or better yet, patch the route module's import.
    
    # We patch routes.agent.secrets.token_urlsafe specifically.
    # If the code was properly refactored, it shouldn't be using this for qr_code anymore.
    # But it MIGHT use it for 'guest_token' (which is secrets.token_urlsafe(32)).
    
    # Strategy:
    # 1. Spy on utils.qr_codes.generate_unique_code to ensure it IS called.
    # 2. Spy on routes.agent.secrets.token_urlsafe to ensure it is NOT called with length < 32.
    
    with patch('utils.qr_codes.generate_unique_code', side_effect=lambda db, length=12: "UNIQUE123456") as mock_global_gen:
        # We also need to allow secrets.token_urlsafe for guest tokens (length 32) if the logic hits it 
        # (though our test user is authenticated, so guest_token logic might be skipped).
        
        # NOTE: If routes/agent.py still imports secrets and uses it for qr_code, we want to fail.
        # But we can't easily distinguish callers without stack inspection.
        # Simpler check: Mock secrets.token_urlsafe in routes.agent to FAIL if length != 32
        
        def strict_token_urlsafe(nbytes=None):
            if nbytes != 32: # Allow guest_token (32) but ban qr_code (9 or 12)
                raise AssertionError(f"Direct usage of secrets.token_urlsafe({nbytes}) forbidden in routes.agent! Use utils.qr_codes.generate_unique_code instead.")
            return "safe_guest_token" * 4 

        with patch('routes.agent.secrets.token_urlsafe', side_effect=strict_token_urlsafe):
            resp = client.post('/submit', data={
                'address': '123 Unique Code Rd',
                'beds': '3',
                'baths': '2',
                'agent_name': 'QR Agent',
                'brokerage': 'Brok',
                'email': 'qr@example.com',
                'phone': '555-1234'
            })
            
            assert resp.status_code in (200, 302)
            
            # Verify global generator was called for property code generation.
            assert mock_global_gen.call_count >= 1
            assert mock_global_gen.call_args.kwargs.get('length') == 12
            
            # Verify property persisted with the mocked code
            prop = db.execute("SELECT qr_code FROM properties WHERE address = '123 Unique Code Rd'").fetchone()
            assert prop['qr_code'] == "UNIQUE123456"


def test_variant_creation_uses_global_generator(auth_client_with_property, db):
    """
    MANDATORY: Assert that campaign variant creation calls utils.qr_codes.generate_unique_code.
    """
    client = auth_client_with_property['client']
    agent_id = auth_client_with_property['agent_id']
    
    # Create a property first
    prop_id = db.execute(
        "INSERT INTO properties (agent_id, address, qr_code) VALUES (%s, 'Variant St', 'VCODE123') RETURNING id",
        (agent_id,)
    ).fetchone()['id']
    db.commit()
    
    # Create campaign
    client.post(f"/api/properties/{prop_id}/campaigns", data={'name': 'Test Campaign'})
    campaign = db.execute("SELECT id FROM campaigns WHERE property_id = %s", (prop_id,)).fetchone()
    
    # Spy on global generator
    with patch('utils.qr_codes.generate_unique_code', side_effect=lambda db, length=8: "VARCODE8") as mock_global_gen:
        
        # Patch local secrets to fail if used
        with patch('routes.campaigns.secrets.token_urlsafe', side_effect=AssertionError("Do not use secrets.token_urlsafe in campaigns!")):
            
            resp = client.post(f"/api/properties/{prop_id}/variants", data={
                'campaign_id': campaign['id'],
                'label': 'Test Variant'
            })
            
            assert resp.status_code == 302
            
            # Verify global generator called for variant code generation.
            assert mock_global_gen.call_count >= 1
            assert mock_global_gen.call_args.kwargs.get('length') == 8
            
            # Check DB
            variant = db.execute("SELECT code FROM qr_variants WHERE label = 'Test Variant'").fetchone()
            assert variant['code'] == "VARCODE8"
