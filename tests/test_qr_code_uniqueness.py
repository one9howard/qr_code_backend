"""
Tests for QR Code Uniqueness Helper and Option B Enforcement

Verifies:
1. is_code_taken checks all 3 tables
2. generate_unique_code always returns unique code
3. Dashboard create SmartSign does NOT activate
4. Only activate_asset with order_id can activate
"""
import pytest
from utils.qr_codes import is_code_taken, generate_unique_code
from services.smart_signs import SmartSignsService


class TestQRCodeUniqueness:
    
    def test_is_code_taken_finds_sign_assets(self, app, db):
        """Code in sign_assets is detected as taken."""
        # Insert a sign asset with known code
        db.execute("""
            INSERT INTO users (email, password_hash, subscription_status) 
            VALUES ('qr_test1@test.com', 'x', 'active')
        """)
        user_id = db.execute("SELECT id FROM users WHERE email='qr_test1@test.com'").fetchone()[0]
        
        db.execute("""
            INSERT INTO sign_assets (user_id, code, label)
            VALUES (%s, 'ASSET12345', 'Test')
        """, (user_id,))
        db.commit()
        
        assert is_code_taken(db, 'ASSET12345') is True
        assert is_code_taken(db, 'NOTEXIST99') is False
    
    def test_is_code_taken_finds_properties_qr_code(self, app, db):
        """Code in properties.qr_code is detected as taken."""
        # Insert property with qr_code
        db.execute("""
            INSERT INTO users (email, password_hash, subscription_status) 
            VALUES ('qr_test2@test.com', 'x', 'active')
        """)
        user_id = db.execute("SELECT id FROM users WHERE email='qr_test2@test.com'").fetchone()[0]
        
        db.execute("""
            INSERT INTO agents (user_id, name, brokerage, email)
            VALUES (%s, 'Agent', 'Brokerage', 'agent@test.com')
        """, (user_id,))
        agent_id = db.execute("SELECT id FROM agents WHERE user_id=%s", (user_id,)).fetchone()[0]
        
        db.execute("""
            INSERT INTO properties (agent_id, address, beds, baths, slug, qr_code)
            VALUES (%s, '123 Test St', '3', '2', 'test-st', 'PROPCODE123')
        """, (agent_id,))
        db.commit()
        
        assert is_code_taken(db, 'PROPCODE123') is True
        assert is_code_taken(db, 'NOTPROPCODE') is False
    
    def test_is_code_taken_finds_qr_variants(self, app, db):
        """Code in qr_variants.code is detected as taken."""
        # Setup property + variant
        db.execute("""
            INSERT INTO users (email, password_hash, subscription_status) 
            VALUES ('qr_test3@test.com', 'x', 'active')
        """)
        user_id = db.execute("SELECT id FROM users WHERE email='qr_test3@test.com'").fetchone()[0]
        
        db.execute("""
            INSERT INTO agents (user_id, name, brokerage, email)
            VALUES (%s, 'Agent3', 'Brokerage', 'agent3@test.com')
        """, (user_id,))
        agent_id = db.execute("SELECT id FROM agents WHERE user_id=%s", (user_id,)).fetchone()[0]
        
        db.execute("""
            INSERT INTO properties (agent_id, address, beds, baths, slug, qr_code)
            VALUES (%s, '456 Test Ave', '2', '1', 'test-ave', 'MAINCODE')
        """, (agent_id,))
        prop_id = db.execute("SELECT id FROM properties WHERE agent_id=%s", (agent_id,)).fetchone()[0]
        
        db.execute("""
            INSERT INTO qr_variants (property_id, code, label)
            VALUES (%s, 'VARIANT999', 'Test Variant')
        """, (prop_id,))
        db.commit()
        
        assert is_code_taken(db, 'VARIANT999') is True
        assert is_code_taken(db, 'NOTVARIANT') is False
    
    def test_generate_unique_code_avoids_collisions(self, app, db):
        """generate_unique_code uses _candidate_fn for deterministic testing."""
        # Insert a known code
        db.execute("""
            INSERT INTO users (email, password_hash, subscription_status) 
            VALUES ('qr_test4@test.com', 'x', 'active')
        """)
        user_id = db.execute("SELECT id FROM users WHERE email='qr_test4@test.com'").fetchone()[0]
        
        db.execute("""
            INSERT INTO sign_assets (user_id, code, label)
            VALUES (%s, 'TAKENCODE01', 'Taken')
        """, (user_id,))
        db.commit()
        
        # Candidate function returns taken code first, then unique code
        candidates = ['TAKENCODE01', 'TAKENCODE01', 'UNIQUECODE99']
        
        def candidate_gen(attempt):
            return candidates[min(attempt, len(candidates) - 1)]
        
        # Should skip taken codes and return the unique one
        code = generate_unique_code(db, _candidate_fn=candidate_gen)
        assert code == 'UNIQUECODE99'


class TestOptionBEnforcement:
    
    def test_create_asset_always_unactivated(self, app, db):
        """SmartSignsService.create_asset creates unactivated assets."""
        db.execute("""
            INSERT INTO users (email, password_hash, subscription_status) 
            VALUES ('optionb@test.com', 'x', 'active')
        """)
        user_id = db.execute("SELECT id FROM users WHERE email='optionb@test.com'").fetchone()[0]
        db.commit()
        
        # Create without activated param (no longer supported)
        asset = SmartSignsService.create_asset(user_id=user_id)
        
        # Verify it's NOT activated
        row = db.execute("""
            SELECT activated_at FROM sign_assets WHERE id = %s
        """, (asset['id'],)).fetchone()
        
        assert row['activated_at'] is None, "Asset must be unactivated on creation"
    
    def test_activate_asset_requires_order_id(self, app, db):
        """activate_asset sets both activated_at and activation_order_id."""
        db.execute("""
            INSERT INTO users (email, password_hash, subscription_status) 
            VALUES ('activate@test.com', 'x', 'active')
        """)
        user_id = db.execute("SELECT id FROM users WHERE email='activate@test.com'").fetchone()[0]
        db.commit()
        
        # Create asset
        asset = SmartSignsService.create_asset(user_id=user_id)
        
        # Create a mock order
        db.execute("""
            INSERT INTO orders (user_id, order_type, status)
            VALUES (%s, 'smart_sign', 'paid')
        """, (user_id,))
        order_id = db.execute("SELECT id FROM orders WHERE user_id=%s ORDER BY id DESC LIMIT 1", (user_id,)).fetchone()[0]
        db.commit()
        
        # Activate
        SmartSignsService.activate_asset(asset['id'], order_id)
        
        # Verify both fields set
        row = db.execute("""
            SELECT activated_at, activation_order_id FROM sign_assets WHERE id = %s
        """, (asset['id'],)).fetchone()
        
        assert row['activated_at'] is not None, "activated_at should be set"
        assert row['activation_order_id'] == order_id, "activation_order_id should match"
    
    def test_activate_asset_rejects_already_activated(self, app, db):
        """activate_asset raises if asset already activated."""
        db.execute("""
            INSERT INTO users (email, password_hash, subscription_status) 
            VALUES ('double@test.com', 'x', 'active')
        """)
        user_id = db.execute("SELECT id FROM users WHERE email='double@test.com'").fetchone()[0]
        db.commit()
        
        # Create and activate
        asset = SmartSignsService.create_asset(user_id=user_id)
        
        db.execute("""
            INSERT INTO orders (user_id, order_type, status)
            VALUES (%s, 'smart_sign', 'paid')
        """, (user_id,))
        order_id = db.execute("SELECT id FROM orders WHERE user_id=%s ORDER BY id DESC LIMIT 1", (user_id,)).fetchone()[0]
        db.commit()
        
        SmartSignsService.activate_asset(asset['id'], order_id)
        
        # Try to activate again - should raise
        with pytest.raises(ValueError, match="already activated"):
            SmartSignsService.activate_asset(asset['id'], order_id)
