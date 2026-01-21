from flask import Flask, request, redirect, url_for
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from config import UPLOAD_DIR, PROPERTY_PHOTOS_DIR, SECRET_KEY, MAX_CONTENT_LENGTH, TRUST_PROXY_HEADERS, PROXY_FIX_NUM_PROXIES, IS_PRODUCTION, STRIPE_PRICE_MONTHLY, STRIPE_PRICE_ANNUAL, STRIPE_PUBLISHABLE_KEY, SESSION_COOKIE_HTTPONLY, SESSION_COOKIE_SAMESITE, SESSION_COOKIE_SECURE, REMEMBER_COOKIE_HTTPONLY, REMEMBER_COOKIE_SECURE, PREFERRED_URL_SCHEME, STORAGE_BACKEND, INSTANCE_DIR
from database import close_connection
from models import User
import os

# Blueprints
from routes.auth import auth_bp
from routes.public import public_bp
from routes.properties import properties_bp
from routes.orders import orders_bp
from routes.webhook import webhook_bp
from routes.billing import billing_bp
from routes.dashboard import dashboard_bp
from routes.agent import agent_bp
from routes.leads import leads_bp
from routes.account import account_bp
from routes.lead_management import lead_management_bp
from routes.campaigns import campaigns_bp

def create_app(test_config=None):
    print("[App] create_app() called")
    app = Flask(__name__)
    print("[App] Flask app instance created")
    
    # Apply Test Config Overrides (Early)
    if test_config:
        app.config.update(test_config)

    app.config['SECRET_KEY'] = SECRET_KEY
    app.config['UPLOAD_FOLDER'] = UPLOAD_DIR
    app.config['PROPERTY_PHOTOS_FOLDER'] = PROPERTY_PHOTOS_DIR
    app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

    # Setup Structured Logging
    from utils.logger import setup_logger
    setup_logger(app)

    # Health Check (Validates DB connectivity)
    @app.route("/healthz")
    def healthz():
        try:
            from database import get_db
            db = get_db()
            db.execute("SELECT 1").fetchone()
            return {"status": "ok", "db": "connected"}, 200
        except Exception as e:
            return {"status": "error", "db": str(e)}, 503

    # Simple ping endpoint for Docker health checks
    @app.route("/ping")
    def ping():
        return {"status": "ok"}, 200

    # ProxyFix
    if IS_PRODUCTION and TRUST_PROXY_HEADERS:
        from werkzeug.middleware.proxy_fix import ProxyFix
        n = PROXY_FIX_NUM_PROXIES
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=n, x_proto=n, x_host=n, x_port=n)
        print(f"[Security] ProxyFix enabled for {n} proxies")

    # Extensions
    csrf = CSRFProtect(app)
    app.config["WTF_CSRF_HEADERS"] = ["X-CSRFToken", "X-CSRF-Token"]
    app.config["WTF_CSRF_TIME_LIMIT"] = 3600

    # Stripe Config
    app.config['STRIPE_PRICE_MONTHLY'] = STRIPE_PRICE_MONTHLY
    app.config['STRIPE_PRICE_ANNUAL'] = STRIPE_PRICE_ANNUAL
    app.config['STRIPE_PUBLISHABLE_KEY'] = STRIPE_PUBLISHABLE_KEY

    # --- FAIL-FAST PRICING CHECK ---
    # In production/dev (not tests), verify all Stripe Lookup Keys exist.
    if not (os.environ.get('APP_STAGE') == 'test' or os.environ.get('FLASK_ENV') == 'test'):
        try:
            from services.print_catalog import get_all_required_lookup_keys
            from services.stripe_price_resolver import warm_cache
            
            with app.app_context():
                # Check if we have Stripe keys at all first
                if app.config.get('STRIPE_SECRET_KEY'):
                    print("[Startup] Warming Stripe Price Cache...")
                    keys = get_all_required_lookup_keys()
                    warm_cache(keys)
                else:
                    print("[Startup] WARNING: No Stripe keys found. Skipping price cache warmup.")
        except Exception as e:
            print(f"[Startup] CRITICAL: Failed to verify Stripe Pricing configuration: {e}")
            raise RuntimeError(f"Pricing Configuration Error: {e}")

    # Template Helpers
    from utils.template_helpers import get_storage_url
    app.jinja_env.globals.update(get_storage_url=get_storage_url)

    # Security Config
    app.config['SESSION_COOKIE_HTTPONLY'] = SESSION_COOKIE_HTTPONLY
    app.config['SESSION_COOKIE_SAMESITE'] = SESSION_COOKIE_SAMESITE
    app.config['SESSION_COOKIE_SECURE'] = SESSION_COOKIE_SECURE
    app.config['REMEMBER_COOKIE_HTTPONLY'] = REMEMBER_COOKIE_HTTPONLY
    app.config['REMEMBER_COOKIE_SECURE'] = REMEMBER_COOKIE_SECURE
    app.config['PREFERRED_URL_SCHEME'] = PREFERRED_URL_SCHEME

    # Database Teardown
    app.teardown_appcontext(close_connection)
    
    # Login Manager
    login_manager = LoginManager()
    login_manager.login_view = 'auth.login'
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return User.get(user_id)

    # Blueprints
    app.register_blueprint(public_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(properties_bp)
    app.register_blueprint(agent_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(orders_bp)
    app.register_blueprint(billing_bp)
    app.register_blueprint(webhook_bp)
    app.register_blueprint(leads_bp)
    app.register_blueprint(account_bp)
    app.register_blueprint(lead_management_bp)
    app.register_blueprint(campaigns_bp)
    
    from routes.printing import printing_bp
    app.register_blueprint(printing_bp)
    
    from routes.smart_signs import smart_signs_bp
    app.register_blueprint(smart_signs_bp)

    from routes.smart_riser import smart_riser_bp
    app.register_blueprint(smart_riser_bp)

    from routes.listing_kits import listing_kits_bp
    app.register_blueprint(listing_kits_bp)

    # Exemptions
    csrf.exempt(webhook_bp)
    csrf.exempt(leads_bp)
    csrf.exempt(printing_bp)

    # Dev/Admin
    if not IS_PRODUCTION:
        from routes.dev import dev_bp
        app.register_blueprint(dev_bp)
    
    from routes.admin import admin_bp
    app.register_blueprint(admin_bp)

    # CLI Commands
    @app.cli.command("cleanup-expired")
    def cleanup_expired_cmd():
        """Delete expired unpaid properties."""
        from services.cleanup import cleanup_expired_properties
        count = cleanup_expired_properties()
        print(f"Deleted {count} expired properties.")

    # Local Storage Serving (Only for Local Backend)
    if STORAGE_BACKEND != 's3':
        from flask import send_from_directory
        
        @app.route('/uploads/<path:filename>')
        def serve_uploads(filename):
            # Serves from INSTANCE_DIR/uploads
            return send_from_directory(os.path.join(INSTANCE_DIR, 'uploads'), filename)

        @app.route('/qr/<path:filename>')
        def serve_qr(filename):
            # Serves from INSTANCE_DIR/qr
            return send_from_directory(os.path.join(INSTANCE_DIR, 'qr'), filename)

    @app.before_request
    def check_verification():
        if request.endpoint and request.endpoint.startswith('static'):
            return
            
        from flask_login import current_user
        if current_user.is_authenticated and not current_user.is_verified:
            allowed_routes = ['auth.verify_email', 'auth.logout', 'auth.resend_verification']
            if request.endpoint not in allowed_routes:
                return redirect(url_for('auth.verify_email'))

    return app

# WSGI Entry Point
app = create_app()

if __name__ == "__main__":
    app.run(host='0.0.0.0', debug=True)
