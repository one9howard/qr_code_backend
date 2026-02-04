from flask import Flask, request, redirect, url_for
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from config import UPLOAD_DIR, PROPERTY_PHOTOS_DIR, SECRET_KEY, MAX_CONTENT_LENGTH, TRUST_PROXY_HEADERS, PROXY_FIX_NUM_PROXIES, IS_PRODUCTION, STRIPE_PRICE_MONTHLY, STRIPE_PRICE_ANNUAL, STRIPE_PUBLISHABLE_KEY, STRIPE_SECRET_KEY, APP_STAGE, SESSION_COOKIE_HTTPONLY, SESSION_COOKIE_SAMESITE, SESSION_COOKIE_SECURE, REMEMBER_COOKIE_HTTPONLY, REMEMBER_COOKIE_SECURE, PREFERRED_URL_SCHEME, STORAGE_BACKEND, INSTANCE_DIR
from database import close_connection
from models import User
import os
import logging

logger = logging.getLogger(__name__)

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
from routes.events import events_bp

def create_app(test_config=None):
    logger.info("[App] create_app() called")
    app = Flask(__name__)
    logger.info("[App] Flask app instance created")
    
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
        logger.info(f"[Security] ProxyFix enabled for {n} proxies")

    # Extensions
    csrf = CSRFProtect(app)
    app.config["WTF_CSRF_HEADERS"] = ["X-CSRFToken", "X-CSRF-Token"]
    app.config["WTF_CSRF_TIME_LIMIT"] = 3600

    # Stripe Config
    app.config['STRIPE_PRICE_MONTHLY'] = STRIPE_PRICE_MONTHLY
    app.config['STRIPE_PRICE_ANNUAL'] = STRIPE_PRICE_ANNUAL
    app.config['STRIPE_PUBLISHABLE_KEY'] = STRIPE_PUBLISHABLE_KEY
    app.config['STRIPE_SECRET_KEY'] = STRIPE_SECRET_KEY
    app.config['APP_STAGE'] = APP_STAGE

    # Centralized Stripe Init
    from services.stripe_client import init_stripe
    
    # Initialize Stripe (Centralized)
    with app.app_context():
        try:
            init_stripe(app)
        except Exception as e:
            logger.error(f"[BOOT-FATAL] Stripe Init Failed: {e}")
            if app.config.get('APP_STAGE') in ('prod', 'staging'):
                raise e

    # --- FAIL-FAST PRICING CHECK ---
    with app.app_context():
        try:
            # Pragmatic Boot: Only Strict in Prod/Staging
            is_strict = app.config.get('APP_STAGE') in ('prod', 'staging')
            
            if not app.config.get('STRIPE_SECRET_KEY'):
                msg = "Missing STRIPE_SECRET_KEY."
                if is_strict:
                    raise RuntimeError(msg)
                else:
                    logger.warning(f"[Startup] WARNING: {msg} (Dev Mode). Skipping cache.")
            else:
                # Attempt Cache Warm
                try:
                    logger.info("[Startup] Warming Stripe Price Cache...")
                    from services.stripe_price_resolver import warm_cache
                    from services.print_catalog import get_all_required_lookup_keys
                    warm_cache(get_all_required_lookup_keys())
                except Exception as e:
                    if is_strict:
                        raise RuntimeError(f"Pricing Cache Failed: {e}")
                    else:
                        logger.warning(f"[Startup] Dev Warning: Cache warm failed: {e}")

        except Exception as e:
            # Fatal boot error
            if app.config.get('APP_STAGE') in ('prod', 'staging'):
                logger.critical(f"[BOOT-FATAL] Configuration Error: {e}")
                raise RuntimeError(f"Configuration Error: {e}")
            else:
                logger.critical(f"[Startup] CRITICAL (Dev Ignored): {e}")

    # Runtime migration removed - use 'python migrate_v2.py' instead
    # with app.app_context():
    #     try:
    #         from services.migration import ensure_agent_columns
    #         ensure_agent_columns()
    #     except Exception as e:
    #         print(f"[Startup] Migration Failed: {e}")

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
    app.register_blueprint(events_bp)
    
    from routes.printing import printing_bp
    app.register_blueprint(printing_bp)
    
    from routes.smart_signs import smart_signs_bp
    app.register_blueprint(smart_signs_bp)

    # SmartRiser - behind feature flag (not fully implemented)
    from config import ENABLE_SMART_RISER
    if ENABLE_SMART_RISER:
        from routes.smart_riser import smart_riser_bp
        app.register_blueprint(smart_riser_bp)

    from routes.listing_kits import listing_kits_bp
    app.register_blueprint(listing_kits_bp)

    from routes.storage_files import storage_files_bp
    app.register_blueprint(storage_files_bp)

    from routes.branding import branding_bp
    app.register_blueprint(branding_bp)

    # Exemptions
    csrf.exempt(webhook_bp)
    csrf.exempt(leads_bp)
    csrf.exempt(printing_bp)
    # csrf.exempt(branding_bp)  # Enforce CSRF for branding
    csrf.exempt(events_bp)  # Public pages post client events without CSRF token

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
            
        # 1. Verification Check
        from flask_login import current_user
        if current_user.is_authenticated and not current_user.is_verified:
            allowed_routes = [
                'auth.verify_email', 'auth.logout', 'auth.resend_verification',
                # Allow Checkout Flows
                'billing.start_checkout', 'billing.checkout', 'billing.portal',
                'orders.order_sign', 'orders.order_success', 'orders.order_cancel',
                'listing_kits.start_kit', 'listing_kits.download_kit',
                # Allow Webhooks (though usually auth exempt anyway)
                'webhook.stripe_webhook'
            ]
            if request.endpoint and request.endpoint not in allowed_routes:
                return redirect(url_for('auth.verify_email'))
    
    @app.before_request
    def request_correlation():
        import uuid
        from flask import g
        
        # 1. Request ID
        req_id = request.headers.get("X-Request-ID")
        if not req_id:
            req_id = str(uuid.uuid4())
        g.request_id = req_id
        
        # 2. Session ID (Correlation)
        sid = request.cookies.get('sid')
        if not sid:
            sid = str(uuid.uuid4())
            g.set_sid_cookie = True # Signal to after_request
        else:
            g.set_sid_cookie = False
        g.sid = sid

    @app.after_request
    def session_cookie_middleware(response):
        from flask import g
        # Apply SID cookie if needed
        if getattr(g, 'set_sid_cookie', False) and hasattr(g, 'sid'):
            import datetime
            # 90 days
            expires = datetime.datetime.now() + datetime.timedelta(days=90)
            secure = app.config.get('SESSION_COOKIE_SECURE', False)
            response.set_cookie(
                'sid', g.sid,
                expires=expires,
                httponly=True,
                samesite='Lax',
                secure=secure
            )
        return response

    from routes.cron import cron_bp
    app.register_blueprint(cron_bp)

    return app

# WSGI Entry Point
# WSGI Entry Point
import traceback

try:
    app = create_app()
except Exception as e:
    logging.getLogger(__name__).critical(f"[BOOT-FATAL] create_app failed: {type(e).__name__}: {e}", exc_info=True)
    raise

if __name__ == "__main__":
    app.run(host='0.0.0.0', debug=True)
