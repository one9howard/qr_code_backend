import secrets
from database import get_db
from services.subscriptions import is_subscription_active

class SmartSignsService:
    @staticmethod
    def create_asset(user_id, label=None, active_property_id=None):
        """
        Create a new Sign Asset.
        Strict Requirement: User must be PRO.
        """
        db = get_db()
        
        # 1. Check Subscription Status (Strict)
        user = db.execute("SELECT subscription_status FROM users WHERE id = %s", (user_id,)).fetchone()
        
        # Must verify user exists first
        if not user:
             raise ValueError("User not found.")
             
        # Canonical entitlement check
        if not is_subscription_active(user['subscription_status']):
             raise PermissionError("Upgrade required: Only Pro users can create SmartSigns.")

        # 2. Generate Unique Code (Global Uniqueness Check)
        while True:
            code = secrets.token_urlsafe(9)[:12] # 12 chars
            
            # Check sign_assets
            if db.execute("SELECT 1 FROM sign_assets WHERE code = %s", (code,)).fetchone():
                continue
                
            # Check properties (legacy qr_code)
            if db.execute("SELECT 1 FROM properties WHERE qr_code = %s", (code,)).fetchone():
                continue
                
            # Check qr_variants (Phase 2)
            if db.execute("SELECT 1 FROM qr_variants WHERE code = %s", (code,)).fetchone():
                continue
                
            # If we get here, it's unique
            break
        
        # 3. Insert Asset
        # Returning ID to confirm creation
        row = db.execute(
            """
            INSERT INTO sign_assets (user_id, code, label, active_property_id)
            VALUES (%s, %s, %s, %s)
            RETURNING id, code, label, is_frozen
            """,
            (user_id, code, label, active_property_id)
        ).fetchone()
        db.commit()
        return row

    @staticmethod
    def assign_asset(asset_id, property_id, user_id):
        """
        Assigns or Reassigns a Sign Asset to a Property.
        Strict Requirements:
          - User must own the Asset.
          - User must own the Property (if property_id is not None).
          - User must be PRO.
          - Asset must NOT be frozen.
        """
        db = get_db()
        
        # 1. Fetch Asset & Verify Ownership
        asset = db.execute("SELECT * FROM sign_assets WHERE id = %s", (asset_id,)).fetchone()
        if not asset:
            raise ValueError("Asset not found.")
        if asset['user_id'] != user_id:
            raise PermissionError("Access denied: You do not own this asset.")
            
        # 2a. Check Frozen Status
        if asset['is_frozen']:
            raise ValueError("Asset is frozen. Reactivate Pro subscription to reassign.")
            
        # 2b. Check Activation Status (Option B)
        # "Asset must be activated (activated_at set) to be assignable"
        if asset['activated_at'] is None:
             raise ValueError("This reusable sign must be activated by a SmartSign purchase before it can be assigned.")

        # 3. Check Subscription (Strict for Assignment too)
        user = db.execute("SELECT subscription_status FROM users WHERE id = %s", (user_id,)).fetchone()
        
        # Canonical check
        if not user or not is_subscription_active(user['subscription_status']):
            raise PermissionError("Upgrade required: Only Pro users can assign SmartSigns.")

        # 4. Verify Property Ownership (if assigning)
        if property_id is not None:
            # Check if property exists and belongs to an agent owned by this user
            prop = db.execute("""
                SELECT p.id 
                FROM properties p
                JOIN agents a ON p.agent_id = a.id
                WHERE p.id = %s AND a.user_id = %s
            """, (property_id, user_id)).fetchone()
            
            if not prop:
                raise ValueError("Property not found or access denied.")

        # 5. Check for Change (Idempotency / History optimization)
        old_property_id = asset['active_property_id']
        if old_property_id == property_id:
            return asset # No change
            
        # 6. Update Asset
        db.execute(
            "UPDATE sign_assets SET active_property_id = %s, updated_at = now() WHERE id = %s",
            (property_id, asset_id)
        )
        
        # 7. Write History
        db.execute(
            """
            INSERT INTO sign_asset_history 
            (sign_asset_id, old_property_id, new_property_id, changed_by_user_id)
            VALUES (%s, %s, %s, %s)
            """,
            (asset_id, old_property_id, property_id, user_id)
        )
        db.commit()
        
        # Return updated asset
        return db.execute("SELECT * FROM sign_assets WHERE id = %s", (asset_id,)).fetchone()

    @staticmethod
    def get_user_assets(user_id):
        db = get_db()
        return db.execute("""
            SELECT sa.*, 
                   p.address as property_address,
                   (SELECT COUNT(*) FROM qr_scans qs WHERE qs.sign_asset_id = sa.id) as scan_count
            FROM sign_assets sa
            LEFT JOIN properties p ON sa.active_property_id = p.id
            WHERE sa.user_id = %s
            ORDER BY sa.created_at DESC
        """, (user_id,)).fetchall()

    @staticmethod
    def resolve_asset(code):
        """
        Resolves an asset code to its destination.
        Returns (asset_row, property_row).
        If asset exists but unassigned, property_row is None.
        If asset does not exist, returns (None, None).
        """
        db = get_db()
        asset = db.execute("SELECT * FROM sign_assets WHERE code = %s", (code,)).fetchone()
        
        if not asset:
            return None, None
            
        property_row = None
        if asset['active_property_id']:
            property_row = db.execute("SELECT * FROM properties WHERE id = %s", (asset['active_property_id'],)).fetchone()
            
        return asset, property_row
