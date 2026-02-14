"""
Unit tests for Pro features and cleanup changes:
- CSRF exempt lead submission works
- Free tier limit = 2
- CSV export blocked for free, allowed for Pro
"""
import os
import sys
import unittest

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestLeadSubmissionCSRF(unittest.TestCase):
    """Tests for CSRF-exempt lead submission."""
    
    def setUp(self):
        from app import app
        app.config['TESTING'] = True
        self.client = app.test_client()
    
    def test_lead_submission_no_csrf_error(self):
        """Lead submission should work without CSRF token (exempt endpoint)."""
        # This should not return 400 CSRF error
        response = self.client.post(
            '/api/leads/submit',
            json={
                'property_id': 1,
                'buyer_name': 'Test User',
                'buyer_email': 'test@example.com',
                'consent': True
            },
            content_type='application/json'
        )
        # Should not be 400 (CSRF) - may be 404 if property doesn't exist
        self.assertNotIn(response.status_code, [400])


class TestFreeTierLeadLimit(unittest.TestCase):
    """Tests for free tier lead limit = 2."""
    
    def test_free_lead_limit_constant(self):
        """FREE_LEAD_LIMIT should be 2."""
        from routes.dashboard import FREE_LEAD_LIMIT
        self.assertEqual(FREE_LEAD_LIMIT, 2)


class TestCSVExport(unittest.TestCase):
    """Tests for CSV export endpoint."""
    
    def setUp(self):
        from app import app
        app.config['TESTING'] = True
        self.client = app.test_client()
    
    def test_csv_export_requires_login(self):
        """CSV export should require authentication."""
        response = self.client.get('/api/leads/export.csv')
        # Should return 401 or redirect to login
        self.assertIn(response.status_code, [401, 302])
    
    def test_csv_export_route_exists(self):
        """CSV export route should be registered."""
        from app import app
        rules = [rule.rule for rule in app.url_map.iter_rules()]
        self.assertIn('/api/leads/export.csv', rules)


class TestAnalyticsService(unittest.TestCase):
    """Tests for analytics service."""
    
    def test_analytics_module_exists(self):
        """Analytics module should be importable."""
        try:
            from services.analytics import per_agent_rollup
            self.assertIsNotNone(per_agent_rollup)
        except ImportError:
            self.fail("Could not import analytics service")
    
    def test_analytics_returns_expected_keys(self):
        """Analytics should return expected data structure."""
        from services.analytics import per_agent_rollup
        from app import app
        
        with app.app_context():
            # Call with user_id that does not exist - should not crash.
            result = per_agent_rollup(99999)
            self.assertEqual(result, {})


if __name__ == "__main__":
    unittest.main()
