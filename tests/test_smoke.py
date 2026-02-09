import pytest
from unittest.mock import patch, MagicMock
import io

def test_healthz(client):
    """Smoke Test: Application health check responds."""
    response = client.get('/healthz')
    assert response.status_code == 200
    assert response.json == {'status': 'ok', 'db': 'connected'}

def test_homepage(client):
    """Smoke Test: App boots and serves public content."""
    response = client.get('/', follow_redirects=True)
    assert response.status_code == 200
    assert b'<!DOCTYPE html>' in response.data

def test_qr_generation():
    """Smoke Test: QR generation produces valid PNG bytes."""
    from utils.qr_image import render_qr_png
    png_bytes = render_qr_png('https://example.com')
    assert png_bytes.startswith(b'\x89PNG')

def test_smartsign_pdf_generation(app):
    """Smoke Test: SmartSign PDF generation works."""
    from services.pdf_smartsign import generate_smartsign_pdf
    
    # Mock storage to avoid any network/disk calls
    with patch('services.pdf_smartsign.get_storage') as mock_get_storage:
        mock_storage = MagicMock()
        mock_get_storage.return_value = mock_storage
        
        # Minimal payload required by PDF generator
        payload = {
            'headline': 'Test House',
            'agent_name': 'Test Agent',
            'agent_phone': '555-0123',
            'agent_email': 'test@example.com',
            'agent_license': 'LIC-123',
            'brokerage_name': 'Test Brokerage',
            'qr_code': b'fake_qr_bytes',
            'bullets': ['Bullet 1', 'Bullet 2'],
            'colors': {'primary': '#003366', 'secondary': '#FFFFFF'},
            'style': 'modern',
            'cta_text': 'Scan for Info'
        }
        
        # The function returns the STORAGE KEY, not the bytes
        pdf_key = generate_smartsign_pdf(payload)
        assert isinstance(pdf_key, str)
        # Defaults to 'smart_v1_minimal' layout
        assert pdf_key.endswith('_smart_v1_minimal.pdf')
        
        # Verify what was put into storage
        args, kwargs = mock_storage.put_file.call_args
        # args[0] is the buffer
        buffer = args[0]
        content = buffer.getvalue()
        assert content.startswith(b'%PDF')
