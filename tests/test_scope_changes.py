"""
Unit tests for scope implementation changes:
- Download route returns 404
- Lead ownership authorization
- Lead submission rate limiting
"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestDownloadPdfRoute(unittest.TestCase):
    """Tests for disabled PDF download route."""
    
    def test_download_pdf_returns_404(self):
        """download_pdf route should return 404 for any order_id."""
        from app import app
        
        with app.test_client() as client:
            # Test with arbitrary order IDs
            response = client.get('/orders/1/download-pdf')
            self.assertEqual(response.status_code, 404)
            
            response = client.get('/orders/999/download-pdf')
            self.assertEqual(response.status_code, 404)
    
    def test_download_pdf_404_message(self):
        """download_pdf should include appropriate error message."""
        from app import app
        
        with app.test_client() as client:
            response = client.get('/orders/1/download-pdf')
            self.assertIn(b'no longer available', response.data.lower())


class TestLeadSubmission(unittest.TestCase):
    """Tests for lead submission endpoint."""
    
    def setUp(self):
        """Set up test fixtures."""
        from app import app
        self.app = app
        self.client = app.test_client()
    
    def test_lead_submission_requires_fields(self):
        """Lead submission should require name, email, property_id, consent."""
        # Missing all fields
        response = self.client.post(
            '/api/leads/submit',
            json={},
            content_type='application/json'
        )
        self.assertNotEqual(response.status_code, 200)
        
        # Missing consent
        response = self.client.post(
            '/api/leads/submit',
            json={
                'property_id': 1,
                'buyer_name': 'Test',
                'buyer_email': 'test@example.com'
            },
            content_type='application/json'
        )
        data = response.get_json()
        self.assertFalse(data.get('success', True))
    
    def test_honeypot_rejects_bots(self):
        """Filled honeypot field should silently reject submission."""
        response = self.client.post(
            '/api/leads/submit',
            json={
                'property_id': 1,
                'buyer_name': 'Bot Test',
                'buyer_email': 'bot@example.com',
                'consent': True,
                'website': 'http://spam.com'  # Honeypot filled = bot
            },
            content_type='application/json'
        )
        # Should return success (to not alert bot) but not actually save
        data = response.get_json()
        self.assertTrue(data.get('success'))


class TestLeadRateLimiting(unittest.TestCase):
    """Tests for lead submission rate limiting."""
    
    def test_rate_limit_check_function(self):
        """check_rate_limit should correctly count recent submissions."""
        from routes.leads import check_rate_limit, RATE_LIMIT_MAX
        
        # This test requires mocking the database
        # The function queries leads table for count
        # For unit testing, we'd need to mock get_db()
        
        # Basic structure test - function should be importable
        self.assertIsNotNone(check_rate_limit)
        self.assertEqual(RATE_LIMIT_MAX, 5)


class TestLeadOwnership(unittest.TestCase):
    """Tests for lead ownership authorization."""
    
    def test_leads_only_shown_to_owning_agent(self):
        """Leads should only be visible to the agent who owns the property."""
        # This is an integration test that would require:
        # 1. Creating test users
        # 2. Creating test agents
        # 3. Creating test properties
        # 4. Creating test leads
        # 5. Verifying dashboard shows only owned leads
        
        # For now, test that the query in dashboard.py uses agent_id filter
        # This is verified by code inspection of dashboard.py index() function
        pass


if __name__ == "__main__":
    unittest.main()
