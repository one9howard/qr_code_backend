
import pytest
from flask import url_for
from unittest.mock import patch, MagicMock
from werkzeug.security import generate_password_hash


def _force_login(client, db, email='test@example.com'):
    row = db.execute(
        """
        INSERT INTO users (email, password_hash, is_verified, subscription_status)
        VALUES (%s, %s, %s, %s)
        RETURNING id
        """,
        (email, generate_password_hash('TestPassword123!'), True, 'active'),
    ).fetchone()
    user_id = row['id']
    db.execute(
        "INSERT INTO agents (user_id, name, brokerage, email, phone) VALUES (%s, %s, %s, %s, %s)",
        (user_id, 'Test Agent', 'Test Brokerage', email, '555-111-2222'),
    )
    db.commit()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user_id)
        sess['_fresh'] = True
    return user_id

@pytest.fixture
def mock_db_cursor(mocker):
    mock_conn = mocker.patch('routes.dashboard.get_db')
    mock_cursor = MagicMock()
    mock_conn.return_value.cursor.return_value = mock_cursor
    mock_conn.return_value.execute.return_value = mock_cursor
    mock_conn.return_value.commit.return_value = None
    return mock_cursor

def test_new_property_get(client, db):
    _force_login(client, db)
    response = client.get(url_for('dashboard.new_property'))
    assert response.status_code == 200
    assert b"Create Property" in response.data
    assert b"Pricing" not in response.data # check against order flow specifics if any

def test_new_property_post_success(client, db, mock_db_cursor, mocker):
    _force_login(client, db)
    
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
    assert response.location.startswith('/dashboard/')
    assert 'new_property_id=' in response.location
    
    # Verify DB calls
    # 1. Agent fetch
    # 2. Property Insert
    # 3. Slug Update
    # 4. QR Update
    
    assert mock_db_cursor.execute.call_count >= 3

    sql_calls = [c[0][0] for c in mock_db_cursor.execute.call_args_list]
    assert any('INSERT INTO properties' in sql for sql in sql_calls)

def test_new_property_post_free_limit(client, db, mock_db_cursor, mocker):
    _force_login(client, db)
    
    # Mock Free User
    mocker.patch('routes.dashboard.is_subscription_active', return_value=False)
    
    # Mock Limit Reached
    mocker.patch('routes.dashboard.can_create_property', return_value={'allowed': False, 'limit': 1})
    
    data = {'address': '123 Main St'}
    response = client.post(url_for('dashboard.new_property'), data=data)
    
    # Should redirect back to new_property (or show error)
    # The code redirects to 'dashboard.new_property' on error
    assert response.status_code == 302
    assert response.location.endswith('/dashboard/properties/new')
