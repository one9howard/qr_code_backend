import unittest
from unittest.mock import patch, MagicMock
from app import create_app
from database import get_db
import uuid
from models import User
import io

class TestSmartSignsPrinting(unittest.TestCase):
    def setUp(self):
        self.app = create_app({'TESTING': True, 'WTF_CSRF_ENABLED': False})
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()
        
        db = get_db()
        
        # Cleanup from previous failed runs
        db.execute("DELETE FROM users WHERE email IN ('pro@test.com', 'basic@test.com')")
        # Cascade? If not, we might error.
        # But users table usually has cascade on deps.
        # If not, we might need to delete agents first. 
        # But we don't know IDs.
        # We can try to delete users. If foreign key error, we'll see.
        db.commit()
        
        # PRO UUID
        self.pro_id = str(uuid.uuid4())
        
        # Insert User returning ID
        row = db.execute("""
            INSERT INTO users (email, password_hash, subscription_status, is_admin, is_verified, created_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
            RETURNING id
        """, ('pro@test.com', 'hash', 'active', False, True)).fetchone()
        self.pro_id = row['id']
        
        # Insert Agent (Required for Dashboard)
        db.execute("""
            INSERT INTO agents (user_id, name, brokerage, email, phone)
            VALUES (%s, 'Pro Agent', 'Brokerage', 'pro@test.com', '555-1234')
        """, (self.pro_id,))
        
        db.commit()
        
        # Create Assets
        # 1. Active Pro Asset
        row = db.execute(
            """INSERT INTO sign_assets (user_id, code, label, created_at, activated_at, is_frozen, brand_name)
               VALUES (%s, 'PROtest', 'Active Asset', NOW(), NOW(), FALSE, 'Old Brand')
               RETURNING id""",
            (self.pro_id,)
        ).fetchone()
        self.active_asset_id = row['id']
        
        # 2. Frozen Asset
        row = db.execute(
            """INSERT INTO sign_assets (user_id, code, label, created_at, activated_at, is_frozen)
               VALUES (%s, 'FRZtest', 'Frozen Asset', NOW(), NOW(), TRUE)
               RETURNING id""",
            (self.pro_id,)
        ).fetchone()
        self.frozen_asset_id = row['id']
        
        # 3. Basic Asset (Same user, but we will mock accessing as basic user)
        row = db.execute(
            """INSERT INTO sign_assets (user_id, code, label, created_at, activated_at, is_frozen)
               VALUES (%s, 'BSCtest', 'Basic Asset', NOW(), NOW(), FALSE)
               RETURNING id""",
            (self.pro_id,)
        ).fetchone()
        self.basic_asset_id = row['id']
        
        db.commit()

    def tearDown(self):
        db = get_db()
        db.execute("DELETE FROM sign_assets WHERE user_id = %s", (self.pro_id,))
        db.execute("DELETE FROM agents WHERE user_id = %s", (self.pro_id,))
        db.execute("DELETE FROM users WHERE id = %s", (self.pro_id,))
        db.commit()
        self.app_context.pop()

    def login_mock(self, user_id):
        # Set session
        with self.client.session_transaction() as sess:
            sess['_user_id'] = str(user_id)
            sess['_fresh'] = True

    @patch('models.User.get')
    @patch('services.pdf_smartsign.generate_smartsign_pdf')
    @patch('routes.smart_signs.get_storage')
    def test_pro_active_flow(self, mock_storage, mock_generate, mock_user_get):
        """Test full flow for Pro user with active asset."""
        # Setup Mock User
        mock_user = MagicMock(spec=User)
        mock_user.id = self.pro_id
        mock_user.is_authenticated = True
        mock_user.is_active = True
        mock_user.is_anonymous = False
        mock_user.is_verified = True
        mock_user.subscription_status = 'active'
        mock_user.display_name = 'Pro User'
        
        mock_user_get.return_value = mock_user
        
        self.login_mock(self.pro_id)
        
        # 1. Dashboard Load
        resp = self.client.get('/dashboard/')
        self.assertEqual(resp.status_code, 200)
        
        # 2. Edit Page Load
        resp = self.client.get(f'/smart-signs/{self.active_asset_id}/edit')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Edit SmartSign Design', resp.data)

        # 3. Post Update
        # We need to mock get_storage for the POST (image upload handling) too!
        # routes.smart_signs.get_storage is called.
        mock_storage_instance = MagicMock()
        mock_storage.return_value = mock_storage_instance
        # Put file returns key
        mock_storage_instance.put_file.return_value = 'uploads/mock.jpg'
        
        update_data = {
            'brand_name': 'New Brand Name',
            'phone': '555-1234',
            'email': 'agent@pro.com',
            'background_style': 'dark',
            'cta_key': 'scan_to_view'
        }
        resp = self.client.post(f'/smart-signs/{self.active_asset_id}/edit', data=update_data, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'SmartSign design updated', resp.data)
        
        # Verify DB update in Real DB
        db = get_db()
        asset = db.execute(
            "SELECT * FROM sign_assets WHERE id=%s", (self.active_asset_id,)
        ).fetchone()
        self.assertEqual(asset['brand_name'], 'New Brand Name')

        # 4. Preview
        # Setup mocks
        mock_generate.return_value = 'mock/path.pdf'
        # mock_storage is already set up, but we need get_file
        mock_storage_instance.get_file.return_value = io.BytesIO(b'%PDF-1.4 mock pdf content')
        
        resp = self.client.get(f'/smart-signs/{self.active_asset_id}/preview.pdf')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content_type, 'application/pdf')

    @patch('models.User.get')
    def test_frozen_asset_access(self, mock_user_get):
        """Test access denied for Frozen asset."""
        mock_user = MagicMock(spec=User)
        mock_user.id = self.pro_id
        mock_user.is_authenticated = True
        mock_user.is_active = True
        mock_user.is_verified = True
        mock_user.subscription_status = 'active'
        mock_user_get.return_value = mock_user
        
        self.login_mock(self.pro_id)
        
        # Edit Page -> 403
        resp = self.client.get(f'/smart-signs/{self.frozen_asset_id}/edit')
        self.assertEqual(resp.status_code, 403)

    @patch('models.User.get')
    def test_non_pro_access(self, mock_user_get):
        """Test access denied for Non-Pro User."""
        mock_user = MagicMock(spec=User)
        mock_user.id = self.pro_id
        mock_user.is_authenticated = True
        mock_user.is_active = True
        mock_user.is_verified = True
        mock_user.subscription_status = 'free' # Non-Pro
        mock_user_get.return_value = mock_user
        
        self.login_mock(self.pro_id)
        
        # Edit Page -> 403
        resp = self.client.get(f'/smart-signs/{self.basic_asset_id}/edit')
        self.assertEqual(resp.status_code, 403)
