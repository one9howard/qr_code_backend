
import pytest
from flask import url_for
from unittest.mock import patch, MagicMock

@pytest.fixture
def mock_db_cursor(mocker):
    mock_conn = mocker.patch('routes.dashboard.get_db')
    mock_cursor = MagicMock()
    mock_conn.return_value.cursor.return_value = mock_cursor
    mock_conn.return_value.execute.return_value = mock_cursor
    return mock_cursor

def test_new_property_get(client, auth):
    auth.login()
    response = client.get(url_for('dashboard.new_property'))
    assert response.status_code == 200
    assert b"Create Property" in response.data
    assert b"Pricing" not in response.data # check against order flow specifics if any

def test_new_property_post_success(client, auth, mock_db_cursor, mocker):
    auth.login()
    
    # Mock DB interactions
    mock_db_cursor.fetchone.side_effect = [
        {'id': 1}, # Agent check
        {'id': 101}, # Property Insert result
        None, # Slug uniqueness check (None = unique)
        {'id': 1}, # Asset check for highlight (found one)
    ]
    
    # Mock internal utils
    mocker.patch('routes.dashboard.slugify', return_value='123-main-st')
    mocker.patch('routes.dashboard.generate_unique_code', return_value='ABC123456789')
    mocker.patch('routes.dashboard.utc_iso', return_value='2023-01-01T00:00:00Z')
    
    # Mock Gating/Subs
    mocker.patch('routes.dashboard.is_subscription_active', return_value=True) # Pro user
    
    data = {
        'address': '123 Main St',
        'beds': '3',
        'baths': '2',
        'price': '500000'
    }
    
    response = client.post(url_for('dashboard.new_property'), data=data, follow_redirects=False)
    
    assert response.status_code == 302
    assert response.location.endswith(url_for('dashboard.index') + '#smart-signs-section')
    
    # Verify DB calls
    # 1. Agent fetch
    # 2. Property Insert
    # 3. Slug Update
    # 4. QR Update
    
    assert mock_db_cursor.execute.call_count >= 4
    
    # Check Property Insert args (Address, Beds, Baths, Price)
    insert_call = mock_db_cursor.execute.call_args_list[1]
    assert 'INSERT INTO properties' in insert_call[0][0]
    assert '123 Main St' in insert_call[0][1]
    
    # Check UPDATE slug
    update_slug = mock_db_cursor.execute.call_args_list[2]
    assert 'UPDATE properties SET slug' in update_slug[0][0]
    
    # Check UPDATE qr
    update_qr = mock_db_cursor.execute.call_args_list[3]
    assert 'UPDATE properties SET qr_code' in update_qr[0][0]

def test_new_property_post_free_limit(client, auth, mock_db_cursor, mocker):
    auth.login()
    
    # Mock Free User
    mocker.patch('routes.dashboard.is_subscription_active', return_value=False)
    
    # Mock Limit Reached
    mocker.patch('routes.dashboard.can_create_property', return_value={'allowed': False, 'limit': 1})
    
    data = {'address': '123 Main St'}
    response = client.post(url_for('dashboard.new_property'), data=data)
    
    # Should redirect back to new_property (or show error)
    # The code redirects to 'dashboard.new_property' on error
    assert response.status_code == 302
    assert url_for('dashboard.new_property') in response.location
