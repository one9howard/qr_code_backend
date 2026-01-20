from flask_login import UserMixin
from database import get_db
from services.subscriptions import is_subscription_active

class User(UserMixin):
    def __init__(self, id, email, is_admin=False, is_verified=False, subscription_status='free', stripe_customer_id=None, stripe_subscription_id=None, subscription_end_date=None, full_name=None, username=None):
        self.id = id
        self.email = email
        self.is_admin = is_admin
        self.is_verified = is_verified
        self.subscription_status = subscription_status
        self.stripe_customer_id = stripe_customer_id
        self.stripe_subscription_id = stripe_subscription_id
        self.subscription_end_date = subscription_end_date
        self._full_name = full_name
        self._username = username

    @property
    def is_pro(self):
        """Check if user has an active Pro subscription (canonical)."""
        return is_subscription_active(self.subscription_status)

    @property
    def full_name(self):
        """Return full name with fallback to email prefix"""
        if self._full_name:
            return self._full_name
        return self.email.split('@')[0].replace('.', ' ').replace('_', ' ').title()

    @property
    def display_name(self):
        """Primary display name for UI: username > full_name > email prefix"""
        if self._username:
            return self._username
        return self.full_name

    @property
    def username(self):
        """Return username if set, otherwise None (templates should use display_name)"""
        return self._username

    @staticmethod
    def get(user_id):
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE id = %s", (user_id,)).fetchone()
        if not user:
            return None
        return User(
            id=user['id'], 
            email=user['email'],
            is_admin=bool(dict(user).get('is_admin', 0)),
            is_verified=bool(dict(user).get('is_verified', 0)),
            subscription_status=dict(user).get('subscription_status', 'free'),
            stripe_customer_id=dict(user).get('stripe_customer_id'),
            stripe_subscription_id=dict(user).get('stripe_subscription_id'),
            subscription_end_date=dict(user).get('subscription_end_date'),
            full_name=dict(user).get('full_name'),
            username=dict(user).get('username')
        )
