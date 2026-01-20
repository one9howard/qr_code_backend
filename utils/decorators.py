from functools import wraps
from flask import redirect, url_for, flash
from flask_login import current_user
from datetime import datetime

def require_subscription(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
            
        from services.subscriptions import is_subscription_active
        
        # 1. Check Explicit Active Status (canonical)
        if is_subscription_active(current_user.subscription_status):
            return f(*args, **kwargs)
            
        # 2. Check Grace Period (End Date in Future)
        if current_user.subscription_end_date:
            end_date = current_user.subscription_end_date
            
            # Type safety
            if isinstance(end_date, str):
                try:
                    # Attempt to parse common formats if it comes back as string
                    # e.g. "2023-01-01 12:00:00" or ISO
                    # For simplicty, try to parse or fail
                    if ' ' in end_date:
                         end_date = datetime.strptime(end_date, "%Y-%m-%d %H:%M:%S.%f" if '.' in end_date else "%Y-%m-%d %H:%M:%S")
                    else:
                         end_date = datetime.fromisoformat(end_date)
                except:
                    pass 
            
            if isinstance(end_date, datetime) and end_date > datetime.now():
                return f(*args, **kwargs)

        flash("Active subscription required to access the dashboard.", "warning")
        return redirect(url_for('billing.index'))
    return decorated_function
