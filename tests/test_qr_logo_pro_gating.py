
import pytest
from unittest.mock import patch, MagicMock, ANY
import io

def test_branding_routes_gating(client, auth_headers):
    # Mock subscription check to fail (Free user)
    with patch('services.subscriptions.is_subscription_active', return_value=False):
        # Upload -> 403
        data = {'logo': (io.BytesIO(b"fake"), 'logo.png')}
        resp = client.post('/api/branding/qr-logo', data=data, headers=auth_headers, content_type='multipart/form-data')
        assert resp.status_code == 403
        assert resp.json['error'] == 'pro_required'
        
        # Toggle ON -> 403
        resp = client.post('/api/branding/qr-logo/toggle', json={'use_qr_logo': True}, headers=auth_headers)
        assert resp.status_code == 403
        
        # Toggle OFF -> 200 (Allowed)
        resp = client.post('/api/branding/qr-logo/toggle', json={'use_qr_logo': False}, headers=auth_headers)
        assert resp.status_code == 200
        
        # Delete -> 200 (Allowed)
        resp = client.delete('/api/branding/qr-logo', headers=auth_headers)
        assert resp.status_code == 200

def test_branding_routes_pro(client, auth_headers):
    # Mock subscription check to pass (Pro user)
    with patch('services.subscriptions.is_subscription_active', return_value=True), \
         patch('services.branding.save_qr_logo', return_value={'key': 'foo'}), \
         patch('services.branding.set_use_qr_logo') as mock_toggle:
        
        # Upload -> 200
        data = {'logo': (io.BytesIO(b"fake"), 'logo.png')}
        # Need to mock normalize too or provide valid image
        # Mocking save_qr_logo bypasses validation
        resp = client.post('/api/branding/qr-logo', data=data, headers=auth_headers, content_type='multipart/form-data')
        assert resp.status_code == 200
        assert resp.json['ok'] is True
        
        # Toggle ON -> 200
        resp = client.post('/api/branding/qr-logo/toggle', json={'use_qr_logo': True}, headers=auth_headers)
        assert resp.status_code == 200
        mock_toggle.assert_called_with(ANY, True)
