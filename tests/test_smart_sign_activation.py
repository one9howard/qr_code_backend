"""
SmartSign Activation Tests

Tests for Option B activation rules per strategy.md:
- Inactive assets (activated_at NULL) cannot redirect
- Active assets redirect to assigned property
"""
import pytest
from services.smart_signs import SmartSignsService


class TestSmartSignActivation:
    
    def test_inactive_asset_scan_returns_not_activated_page(self, app, client, db):
        """
        Scanning an inactive SmartSign should return 200 with Not Activated template.
        NOT a redirect.
        """
        # Setup user
        db.execute("""
            INSERT INTO users (email, password_hash, subscription_status) 
            VALUES ('inactive@test.com', 'x', 'active')
        """)
        user_id = db.execute("SELECT id FROM users WHERE email='inactive@test.com'").fetchone()[0]
        db.commit()
        
        # Create INACTIVE asset (activated_at = NULL)
        asset = SmartSignsService.create_asset_for_purchase(user_id, None, "Inactive Test")
        
        # Verify it's inactive
        row = db.execute("SELECT * FROM sign_assets WHERE id=%s", (asset['id'],)).fetchone()
        assert row['activated_at'] is None
        
        # Scan the asset
        resp = client.get(f"/r/{asset['code']}")
        
        # Should NOT redirect (302), should render page (200)
        assert resp.status_code == 200
        assert b"Not Activated" in resp.data
        assert asset['code'].encode() in resp.data or b"Inactive Test" in resp.data
    
    def test_active_asset_scan_redirects_to_property(self, app, client, db):
        """
        Scanning an ACTIVE and ASSIGNED SmartSign should redirect to /p/<slug>.
        """
        # Setup user + agent + property
        db.execute("""
            INSERT INTO users (email, password_hash, subscription_status) 
            VALUES ('active@test.com', 'x', 'active')
        """)
        user_id = db.execute("SELECT id FROM users WHERE email='active@test.com'").fetchone()[0]
        
        db.execute("""
            INSERT INTO agents (user_id, name, brokerage, email) 
            VALUES (%s, 'Active Agent', 'Brokerage', 'active@agent.com')
        """, (user_id,))
        agent_id = db.execute("SELECT id FROM agents WHERE user_id=%s", (user_id,)).fetchone()[0]
        
        db.execute("""
            INSERT INTO properties (agent_id, address, beds, baths, slug) 
            VALUES (%s, '100 Active St', '3', '2', 'active-property-slug')
        """, (agent_id,))
        prop_id = db.execute("SELECT id FROM properties WHERE agent_id=%s", (agent_id,)).fetchone()[0]
        db.commit()
        
        # Create and ACTIVATE asset
        asset = SmartSignsService.create_asset_for_purchase(user_id, None, "Active Test")
        db.execute("""
            UPDATE sign_assets SET activated_at=NOW(), is_frozen=false WHERE id=%s
        """, (asset['id'],))
        db.commit()
        
        # Assign to property
        SmartSignsService.assign_asset(asset['id'], prop_id, user_id)
        
        # Scan the asset
        resp = client.get(f"/r/{asset['code']}")
        
        # Should redirect (302) to property page
        assert resp.status_code == 302
        assert '/p/active-property-slug' in resp.location
    
    def test_active_unassigned_asset_shows_unassigned_page(self, app, client, db):
        """
        Active but unassigned asset shows unassigned page (not redirect).
        """
        db.execute("""
            INSERT INTO users (email, password_hash, subscription_status) 
            VALUES ('unassigned@test.com', 'x', 'active')
        """)
        user_id = db.execute("SELECT id FROM users WHERE email='unassigned@test.com'").fetchone()[0]
        db.commit()
        
        # Create and activate, but don't assign
        asset = SmartSignsService.create_asset_for_purchase(user_id, None, "Unassigned Active")
        db.execute("""
            UPDATE sign_assets SET activated_at=NOW(), is_frozen=false WHERE id=%s
        """, (asset['id'],))
        db.commit()
        
        # Scan
        resp = client.get(f"/r/{asset['code']}")
        
        # Should show unassigned page (200), not redirect
        assert resp.status_code == 200
        assert b"Not Assigned" in resp.data
    
    def test_assignment_blocked_for_inactive_asset(self, app, db):
        """
        Attempting to assign an inactive asset should raise ValueError.
        (Already tested in test_smart_signs.py but reinforced here)
        """
        db.execute("""
            INSERT INTO users (email, password_hash, subscription_status) 
            VALUES ('block@test.com', 'x', 'active')
        """)
        user_id = db.execute("SELECT id FROM users WHERE email='block@test.com'").fetchone()[0]
        
        db.execute("""
            INSERT INTO agents (user_id, name, brokerage, email) 
            VALUES (%s, 'Block Agent', 'Brokerage', 'block@agent.com')
        """, (user_id,))
        agent_id = db.execute("SELECT id FROM agents WHERE user_id=%s", (user_id,)).fetchone()[0]
        
        db.execute("""
            INSERT INTO properties (agent_id, address, beds, baths, slug) 
            VALUES (%s, '200 Block St', '2', '1', 'block-street')
        """, (agent_id,))
        prop_id = db.execute("SELECT id FROM properties WHERE agent_id=%s", (agent_id,)).fetchone()[0]
        db.commit()
        
        # Create INACTIVE asset
        asset = SmartSignsService.create_asset_for_purchase(user_id, None, "Should Block")
        
        # Attempt to assign should raise
        with pytest.raises(ValueError, match="activated"):
            SmartSignsService.assign_asset(asset['id'], prop_id, user_id)
    
    def test_unassigned_active_asset_scan_logs_to_app_events(self, app, client, db):
        """
        Unassigned SmartSign scans log to app_events (Option 2).
        Event type: smart_sign_scan, source: server
        """
        # Setup user
        db.execute("""
            INSERT INTO users (email, password_hash, subscription_status) 
            VALUES ('scan_log@test.com', 'x', 'active')
        """)
        user_id = db.execute("SELECT id FROM users WHERE email='scan_log@test.com'").fetchone()[0]
        db.commit()
        
        # Create and activate asset (but don't assign)
        asset = SmartSignsService.create_asset_for_purchase(user_id, None, "Scan Log Test")
        db.execute("""
            UPDATE sign_assets SET activated_at=NOW(), is_frozen=false WHERE id=%s
        """, (asset['id'],))
        db.commit()
        
        # Scan the unassigned asset
        resp = client.get(f"/r/{asset['code']}")
        assert resp.status_code == 200  # Unassigned page
        
        # Verify scan was logged to app_events
        event = db.execute("""
            SELECT * FROM app_events 
            WHERE event_type = 'smart_sign_scan' 
              AND sign_asset_id = %s
            ORDER BY occurred_at DESC LIMIT 1
        """, (asset['id'],)).fetchone()
        
        assert event is not None, "smart_sign_scan event should be logged"
        assert event['source'] == 'server'
        assert event['sign_asset_id'] == asset['id']

