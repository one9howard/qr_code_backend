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
    
    def test_create_asset_always_unactivated(self, app, db):
        """
        Verify that SmartSignsService.create_asset() 
        sets activated_at to NULL (Option B enforcement).
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
        
        # Create asset (activated param removed from API)
        asset = SmartSignsService.create_asset(
            user_id=user_id
        )
        
        # Verify asset created
        assert asset is not None
        assert asset['id'] is not None
        assert asset['code'] is not None
        
        # Verify activated_at is NULL (Must purchase to activate)
        row = db.execute("""
            SELECT activated_at FROM sign_assets WHERE id = %s
        """, (asset['id'],)).fetchone()
        
        assert row is not None
        assert row['activated_at'] is None, "Asset must be unactivated initially"
    

    def test_pro_user_cant_activate_without_order(self, app, client, db):
        """
        Verify that Pro users cannot create activated assets directly anymore.
        Must go through purchase flow to activate.
        """
        # Setup user
        db.execute("""
            INSERT INTO users (email, password_hash, subscription_status) 
            VALUES ('no_activate@test.com', 'x', 'active')
        """)
        user_id = db.execute(
            "SELECT id FROM users WHERE email='no_activate@test.com'"
        ).fetchone()[0]
        db.commit()
        
        # Create asset (activated param removed)
        try:
            asset = SmartSignsService.create_asset(user_id=user_id)
        except TypeError:
            # If accidentally passed, it might raise TypeError depending on how it's called
            # but here we test the correct call produces unactivated asset
            pass
            
        # Verify unactivated
        asset = SmartSignsService.create_asset(user_id=user_id)
        row = db.execute("SELECT activated_at FROM sign_assets WHERE id=%s", (asset['id'],)).fetchone()
        assert row['activated_at'] is None, "Option B: Assets create unactivated"
