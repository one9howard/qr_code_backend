import pytest
from unittest.mock import MagicMock, patch
from flask import Flask, url_for
from flask_login import LoginManager

# minimal app to register blueprint
from routes.dashboard import dashboard_bp
from routes.smart_signs import smart_signs_bp

@pytest.fixture
def mock_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'test'
    app.config['SERVER_NAME'] = 'localhost'
    app.config['LOGIN_DISABLED'] = True
    
    login_manager = LoginManager()
    login_manager.init_app(app)
    
    @login_manager.user_loader
    def load_user(user_id):
        return MagicMock(is_authenticated=True, id=user_id)
    
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(smart_signs_bp)
    
    return app

@pytest.fixture
def client(mock_app):
    return mock_app.test_client()

def test_progress_assign_next_step_points_to_dashboard_anchor(client, mock_app):
    """
    Test P0-1: The progress 'Assign SmartSign' CTA should link to the dashboard
    anchor with highlight param, NOT the editor.
    """
    with patch('routes.dashboard.get_db') as mock_get_db, \
         patch('routes.dashboard.login_required', lambda x: x), \
         patch('routes.dashboard.current_user') as mock_user, \
         patch('services.analytics.per_agent_rollup') as mock_rollup, \
         patch('services.analytics.per_property_metrics') as mock_prop_metrics, \
         patch('services.smart_signs.SmartSignsService.get_user_assets') as mock_get_assets, \
         patch('routes.dashboard.render_template') as mock_render:
        
        # Setup User
        mock_user.id = 1
        mock_user.is_pro = True
        
        # Setup DB (mocking queries in dashboard.index)
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.execute.return_value.fetchall.return_value = []
        # Return generic dict for fetchone stats
        mock_db.execute.return_value.fetchone.return_value = {'count': 0, 'total': 0, 'latest': None, 'id': 1}
        
        # Setup SmartSigns: One UNASSIGNED sign
        mock_asset = {
            'id': 101,
            'active_property_id': None, # Unassigned
            'label': 'Test Sign',
            'code': 'ABC'
        }
        mock_get_assets.return_value = [mock_asset]
        
        # Setup Analytics
        mock_rollup.return_value = {}
        mock_prop_metrics.return_value = {
            'scans': {'total':0, 'delta':0},
            'views': {'total':0, 'delta':0},
            'leads': {'total':0, 'delta':0},
            'ctas': {'total':0, 'delta':0},
            'last_activity': {'summary': ''},
            'insights': []
        }

        # Request
        with mock_app.test_request_context():
             from routes.dashboard import index
             index()
             
             # Inspect context passed to render_template
             args, kwargs = mock_render.call_args
             context = kwargs
             
             next_step_url = context.get('next_step_url')
             print(f"Computed next_step_url: {next_step_url}")
             
             # Expected: /dashboard/?highlight_asset_id=101#smart-signs-section
             assert "highlight_asset_id=101" in next_step_url
             assert "#smart-signs-section" in next_step_url
             assert "edit" not in next_step_url


