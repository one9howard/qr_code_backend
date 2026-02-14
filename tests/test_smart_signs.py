import pytest
from services.smart_signs import SmartSignsService
from database import get_db

class TestSmartSigns:
    
    def _create_active_asset(self, db, user_id, label="Test Asset"):
        # Helper to activate via a real paid order reference (activation_order_id required).
        asset = SmartSignsService.create_asset_for_purchase(user_id, None, label)
        activation_order_id = db.execute(
            """
            INSERT INTO orders (user_id, status, order_type, paid_at, print_product, amount_total_cents, currency)
            VALUES (%s, 'paid', 'smart_sign', NOW(), 'smart_sign', 0, 'usd')
            RETURNING id
            """,
            (user_id,)
        ).fetchone()['id']
        db.commit()
        SmartSignsService.activate_asset(asset['id'], activation_order_id)
        return db.execute("SELECT * FROM sign_assets WHERE id=%s", (asset['id'],)).fetchone()

    def test_pro_create_asset_via_purchase_flow(self, app, db, client):
        """Pro user can create an asset (inactive initially)."""
        # 1. Setup Pro User
        db.execute("INSERT INTO users (email, password_hash, subscription_status) VALUES ('pro@t.com', 'x', 'active') RETURNING id")
        user_id = db.execute("SELECT id FROM users WHERE email='pro@t.com'").fetchone()[0]
        db.commit()

        # 2. Create Asset (simulating checkout start)
        asset = SmartSignsService.create_asset_for_purchase(user_id, None, "Test Label")
        
        assert asset['code'] is not None
        assert asset['label'] == "Test Label"
        
        # Verify DB persistence and Inactive status
        row = db.execute("SELECT * FROM sign_assets WHERE id = %s", (asset['id'],)).fetchone()
        assert row is not None
        assert row['activated_at'] is None  # Should be inactive
        # It might be frozen or not depending on default, but logic says is_frozen=False in create_asset_for_purchase?
        # Let's check impl: "VALUES (..., false)" -> so is_frozen is false.
        assert row['is_frozen'] is False

    def test_pro_assign_asset_to_own_property(self, app, db):
        """Pro user can assign their ACTIVATED asset to their property."""
        # Setup User/Agent/Property
        db.execute("INSERT INTO users (email, password_hash, subscription_status) VALUES ('assign@t.com', 'x', 'active')")
        user_id = db.execute("SELECT id FROM users WHERE email='assign@t.com'").fetchone()[0]
        db.execute("INSERT INTO agents (user_id, name, brokerage, email) VALUES (%s, 'A', 'B', 'a@b.com')", (user_id,))
        agent_id = db.execute("SELECT id FROM agents WHERE user_id=%s", (user_id,)).fetchone()[0]
        db.execute("INSERT INTO properties (agent_id, address, beds, baths) VALUES (%s, '123 Main', '3', '2')", (agent_id,))
        prop_id = db.execute("SELECT id FROM properties WHERE agent_id=%s", (agent_id,)).fetchone()[0]
        db.commit()
        
        # Create ACTIVATED Asset
        asset = self._create_active_asset(db, user_id, "My Sign")
        
        # Assign
        updated = SmartSignsService.assign_asset(asset['id'], prop_id, user_id)
        assert updated['active_property_id'] == prop_id
        
        # Verify History
        hist = db.execute("SELECT * FROM sign_asset_history WHERE sign_asset_id=%s", (asset['id'],)).fetchone()
        assert hist is not None
        assert hist['new_property_id'] == prop_id
        assert hist['changed_by_user_id'] == user_id

    def test_free_can_initial_assign_asset(self, app, db):
        """Free user CAN do initial assignment of activated asset (Practical Mode)."""
        db.execute("INSERT INTO users (email, password_hash, subscription_status) VALUES ('free_initial@t.com', 'x', 'free')")
        user_id = db.execute("SELECT id FROM users WHERE email='free_initial@t.com'").fetchone()[0]
        
        # Create asset (activated, unassigned)
        asset = self._create_active_asset(db, user_id, "Free Initial Sign")
        assert asset['active_property_id'] is None
        
        # Setup Property
        db.execute("INSERT INTO agents (user_id, name, brokerage, email) VALUES (%s, 'A', 'B', 'a@b.com')", (user_id,))
        agent_id = db.execute("SELECT id FROM agents WHERE user_id=%s", (user_id,)).fetchone()[0]
        db.execute("INSERT INTO properties (agent_id, address, beds, baths) VALUES (%s, '123 Main', '3', '2')", (agent_id,))
        prop_id = db.execute("SELECT id FROM properties WHERE agent_id=%s", (agent_id,)).fetchone()[0]
        db.commit()
        
        # Attempt Initial Assign -> Should PASS
        updated = SmartSignsService.assign_asset(asset['id'], prop_id, user_id)
        assert updated['active_property_id'] == prop_id

    def test_free_cannot_reassign_asset(self, app, db):
        """Free user CANNOT reassign asset (change property)."""
        # Start as Pro to make initial setup easy
        db.execute("INSERT INTO users (email, password_hash, subscription_status) VALUES ('reassign@t.com', 'x', 'active')")
        user_id = db.execute("SELECT id FROM users WHERE email='reassign@t.com'").fetchone()[0]
        
        # Setup Properties
        db.execute("INSERT INTO agents (user_id, name, brokerage, email) VALUES (%s, 'A', 'B', 'a@b.com')", (user_id,))
        agent_id = db.execute("SELECT id FROM agents WHERE user_id=%s", (user_id,)).fetchone()[0]
        db.execute("INSERT INTO properties (agent_id, address, beds, baths) VALUES (%s, 'Prop A', '1', '1')", (agent_id,))
        prop_a = db.execute("SELECT id FROM properties WHERE address='Prop A'").fetchone()[0]
        db.execute("INSERT INTO properties (agent_id, address, beds, baths) VALUES (%s, 'Prop B', '1', '1')", (agent_id,))
        prop_b = db.execute("SELECT id FROM properties WHERE address='Prop B'").fetchone()[0]
        db.commit()
        
        # Assign to A (while Pro)
        asset = self._create_active_asset(db, user_id, "Reassign Sign")
        SmartSignsService.assign_asset(asset['id'], prop_a, user_id)
        
        # Downgrade User
        db.execute("UPDATE users SET subscription_status='free' WHERE id=%s", (user_id,))
        db.commit()
        
        # Attempt Reassign to B -> FAIL
        with pytest.raises(PermissionError) as excinfo:
            SmartSignsService.assign_asset(asset['id'], prop_b, user_id)
        
        msg = str(excinfo.value)
        assert "Upgrade required" in msg
        assert "reassign" in msg.lower() # Check both substrings

    def test_free_cannot_unassign_asset(self, app, db):
        """Free user CANNOT unassign asset (set to None)."""
        # Start as Pro
        db.execute("INSERT INTO users (email, password_hash, subscription_status) VALUES ('unassign@t.com', 'x', 'active')")
        user_id = db.execute("SELECT id FROM users WHERE email='unassign@t.com'").fetchone()[0]
        
        # Setup Property
        db.execute("INSERT INTO agents (user_id, name, brokerage, email) VALUES (%s, 'A', 'B', 'a@b.com')", (user_id,))
        agent_id = db.execute("SELECT id FROM agents WHERE user_id=%s", (user_id,)).fetchone()[0]
        db.execute("INSERT INTO properties (agent_id, address, beds, baths) VALUES (%s, 'Prop A', '1', '1')", (agent_id,))
        prop_a = db.execute("SELECT id FROM properties WHERE address='Prop A'").fetchone()[0]
        db.commit()
        
        # Assign to A
        asset = self._create_active_asset(db, user_id, "Unassign Sign")
        SmartSignsService.assign_asset(asset['id'], prop_a, user_id)
        
        # Downgrade
        db.execute("UPDATE users SET subscription_status='free' WHERE id=%s", (user_id,))
        db.commit()
        
        # Attempt Unassign -> FAIL
        with pytest.raises(PermissionError) as excinfo:
            SmartSignsService.assign_asset(asset['id'], None, user_id)
            
        msg = str(excinfo.value)
        assert "Upgrade required" in msg
        assert "reassign" in msg.lower() # Treating unassign as part of "reassign" restriction

    def test_frozen_blocks_assign(self, app, db):
        """Frozen asset cannot be reassigned."""
        db.execute("INSERT INTO users (email, password_hash, subscription_status) VALUES ('frozen@t.com', 'x', 'active')")
        user_id = db.execute("SELECT id FROM users WHERE email='frozen@t.com'").fetchone()[0]
        
        asset = self._create_active_asset(db, user_id, "Frozen Sign")
        
        # Manually freeze
        db.execute("UPDATE sign_assets SET is_frozen=true WHERE id=%s", (asset['id'],))
        db.commit()
        
        with pytest.raises(ValueError, match="Asset is frozen"):
            SmartSignsService.assign_asset(asset['id'], None, user_id)

    def test_inactive_blocks_assign(self, app, db):
        """Inactive asset cannot be reassigned (Option B)."""
        db.execute("INSERT INTO users (email, password_hash, subscription_status) VALUES ('inactive@t.com', 'x', 'active')")
        user_id = db.execute("SELECT id FROM users WHERE email='inactive@t.com'").fetchone()[0]
        
        # Create but DO NOT ACTIVATE
        asset = SmartSignsService.create_asset_for_purchase(user_id, None, "Inactive Sign")
        
        # Attempt Assign
        with pytest.raises(ValueError, match="This reusable sign must be activated"):
            SmartSignsService.assign_asset(asset['id'], None, user_id)

    def test_scan_resolution_flow(self, app, client, db):
        # Setup
        db.execute("INSERT INTO users (email, password_hash, subscription_status) VALUES ('scan@t.com', 'x', 'active')")
        user_id = db.execute("SELECT id FROM users WHERE email='scan@t.com'").fetchone()[0]
        
        # Create Assigned Asset
        asset = self._create_active_asset(db, user_id, "Scan Me")
        
        db.execute("INSERT INTO agents (user_id, name, brokerage, email) VALUES (%s, 'A', 'B', 'a@b.com')", (user_id,))
        agent_id = db.execute("SELECT id FROM agents WHERE user_id=%s", (user_id,)).fetchone()[0]
        db.execute("INSERT INTO properties (agent_id, address, beds, baths, slug) VALUES (%s, 'Scan St', '1', '1', 'scan-st')", (agent_id,))
        prop_id = db.execute("SELECT id FROM properties WHERE address='Scan St'").fetchone()[0]
        db.commit()
        
        SmartSignsService.assign_asset(asset['id'], prop_id, user_id)
        
        # 1. Test Scan -> Redirect
        resp = client.get(f"/r/{asset['code']}")
        assert resp.status_code == 302
        assert '/p/scan-st' in resp.location
        
        # Verify Scan Log
        scan = db.execute("SELECT * FROM qr_scans WHERE sign_asset_id=%s", (asset['id'],)).fetchone()
        assert scan is not None
        assert scan['property_id'] == prop_id

    def test_unassigned_asset_page(self, app, client, db):
        db.execute("INSERT INTO users (email, password_hash, subscription_status) VALUES ('un@t.com', 'x', 'active')")
        user_id = db.execute("SELECT id FROM users WHERE email='un@t.com'").fetchone()[0]
        
        # Need active asset to not be frozen/weird? 
        # Actually unassigned page works even if inactive?
        # Let's test with active for now.
        asset = self._create_active_asset(db, user_id, "Lone Wolf")
        
        # Scan Unassigned
        resp = client.get(f"/r/{asset['code']}")
        assert resp.status_code == 200
        assert b"Not Assigned Yet" in resp.data
        assert b"Lone Wolf" in resp.data
        
        # Verify NO scan log
        scan = db.execute("SELECT * FROM qr_scans WHERE sign_asset_id=%s", (asset['id'],)).fetchone()
        assert scan is None

