import pytest
from app import create_app
import os

@pytest.fixture
def clean_app():
    app = create_app({'TESTING': True, 'CRON_TOKEN': 'secret-test-token'})
    return app

@pytest.fixture
def client(clean_app):
    return clean_app.test_client()

def test_cron_cleanup_no_token(client):
    response = client.post('/cron/cleanup-expired')
    assert response.status_code == 401
    assert response.json == {"success": False, "error": "unauthorized"}

def test_cron_cleanup_wrong_token(client):
    response = client.post('/cron/cleanup-expired', headers={"X-CRON-TOKEN": "wrong"})
    assert response.status_code == 401
    assert response.json == {"success": False, "error": "unauthorized"}

def test_cron_cleanup_success(client, monkeypatch):
    # Mock the actual cleanup service to avoid DB calls
    import services.cleanup
    monkeypatch.setattr(services.cleanup, 'cleanup_expired_properties', lambda: 5)
    
    response = client.post('/cron/cleanup-expired', headers={"X-CRON-TOKEN": "secret-test-token"})
    assert response.status_code == 200
    assert response.json == {"success": True, "deleted": 5}
