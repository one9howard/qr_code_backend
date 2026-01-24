"""
Test SmartSigns Phase 1 end-to-end flow.

Verifies that a Pro user can:
1. Create an asset via dashboard (immediately activated)
2. Assign it to a property
3. Scan /r/<code> and get redirected to the property page
"""
import pytest
from flask_login import login_user
from services.smart_signs import SmartSignsService


class TestSmartSignsPhase1:
    
    def test_create_asset_activated_true_sets_activated_at(self, app, db):
        """
        Verify that SmartSignsService.create_asset(activated=True) 
        sets activated_at to NOW(), not NULL.
        """
        # Setup Pro user
        db.execute("""
            INSERT INTO users (email, password_hash, subscription_status) 
            VALUES ('phase1create@test.com', 'x', 'active')
        """)
        user_id = db.execute(
            "SELECT id FROM users WHERE email='phase1create@test.com'"
        ).fetchone()[0]
        db.commit()
        
        # Create asset with activated=True (Phase 1 Pro flow)
        asset = SmartSignsService.create_asset(
            user_id=user_id,
            activated=True
        )
        
        # Verify asset created
        assert asset is not None
        assert asset['id'] is not None
        assert asset['code'] is not None
        
        # Verify activated_at is NOT NULL
        row = db.execute("""
            SELECT activated_at FROM sign_assets WHERE id = %s
        """, (asset['id'],)).fetchone()
        
        assert row is not None, "Asset should exist in DB"
        assert row['activated_at'] is not None, "activated_at should be set for activated=True"
    
    def test_create_asset_activated_false_leaves_null(self, app, db):
        """
        Verify that SmartSignsService.create_asset(activated=False) 
        leaves activated_at as NULL.
        """
        # Setup Pro user
        db.execute("""
            INSERT INTO users (email, password_hash, subscription_status) 
            VALUES ('phase1draft@test.com', 'x', 'active')
        """)
        user_id = db.execute(
            "SELECT id FROM users WHERE email='phase1draft@test.com'"
        ).fetchone()[0]
        db.commit()
        
        # Create asset with activated=False (purchase flow)
        asset = SmartSignsService.create_asset(
            user_id=user_id,
            activated=False
        )
        
        # Verify activated_at IS NULL
        row = db.execute("""
            SELECT activated_at FROM sign_assets WHERE id = %s
        """, (asset['id'],)).fetchone()
        
        assert row is not None
        assert row['activated_at'] is None, "activated_at should be NULL for activated=False"
    
    def test_pro_user_phase1_full_flow(self, app, client, db):
        """
        End-to-end: Pro creates activated asset -> assigns -> scan redirects.
        """
        # Setup user + agent + property
        db.execute("""
            INSERT INTO users (email, password_hash, subscription_status) 
            VALUES ('phase1flow@test.com', 'x', 'active')
        """)
        user_id = db.execute(
            "SELECT id FROM users WHERE email='phase1flow@test.com'"
        ).fetchone()[0]
        
        db.execute("""
            INSERT INTO agents (user_id, name, brokerage, email) 
            VALUES (%s, 'Phase1 Agent', 'Brokerage', 'phase1@agent.com')
        """, (user_id,))
        agent_id = db.execute("SELECT id FROM agents WHERE user_id=%s", (user_id,)).fetchone()[0]
        
        db.execute("""
            INSERT INTO properties (agent_id, address, beds, baths, slug) 
            VALUES (%s, '123 Phase1 St', '3', '2', 'phase1-prop-slug')
        """, (agent_id,))
        prop_id = db.execute("SELECT id FROM properties WHERE agent_id=%s", (agent_id,)).fetchone()[0]
        db.commit()
        
        # 1. Create ACTIVATED asset via service (simulates dashboard with activated=True)
        asset = SmartSignsService.create_asset(
            user_id=user_id,
            activated=True  # Phase 1: Pro users get immediate activation
        )
        
        # Verify it's activated
        row = db.execute("SELECT * FROM sign_assets WHERE id=%s", (asset['id'],)).fetchone()
        assert row['activated_at'] is not None, "Phase 1 asset should be activated immediately"
        
        # 2. Assign to property
        SmartSignsService.assign_asset(asset['id'], prop_id, user_id)
        
        # 3. Scan and verify redirect
        resp = client.get(f"/r/{asset['code']}")
        assert resp.status_code == 302
        assert '/p/phase1-prop-slug' in resp.location
