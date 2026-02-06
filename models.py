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

class Agent:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
            
    @classmethod
    def get(cls, agent_id):
        db = get_db()
        row = db.execute("SELECT * FROM agents WHERE id = %s", (agent_id,)).fetchone()
        if not row: return None
        return cls(**dict(row))

class Property:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
    
    @classmethod
    def get(cls, property_id):
        db = get_db()
        row = db.execute("SELECT * FROM properties WHERE id = %s", (property_id,)).fetchone()
        if not row: return None
        return cls(**dict(row))

    @property
    def agent(self):
        if hasattr(self, '_agent') and self._agent:
            return self._agent
        if not hasattr(self, 'agent_id') or not self.agent_id:
            return None
        self._agent = Agent.get(self.agent_id)
        return self._agent

class Order:
    ALLOWED_COLUMNS = (
        'id', 'user_id', 'property_id', 'stripe_session_id', 'amount_total', 
        'status', 'print_product', 'print_size', 'material', 'quantity', 
        'shipping_address', 'sign_pdf_path', 'preview_url', 
        'checkout_session_id', 'order_type', 'sign_asset_id', 'design_payload',
        'provider_job_id', 'layout_id', 'created_at', 'updated_at',
        'sign_size', 'sign_color', 'guest_email', 'guest_token'
    )

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            if k in self.ALLOWED_COLUMNS:
                setattr(self, k, v)
            
    @classmethod
    def get(cls, order_id):
        db = get_db()
        row = db.execute("SELECT * FROM orders WHERE id = %s", (order_id,)).fetchone()
        if not row: return None
        return cls(**dict(row))
    
    @classmethod
    def get_by(cls, **kwargs):
        """Simple filter helper (first match)"""
        db = get_db()
        clauses = []
        params = []
        for k, v in kwargs.items():
            clauses.append(f"{k} = %s")
            params.append(v)
        
        where = " AND ".join(clauses)
        sql = f"SELECT * FROM orders WHERE {where} LIMIT 1"
        row = db.execute(sql, tuple(params)).fetchone()
        if not row: return None
        return cls(**dict(row))

    def save(self):
        db = get_db()
        from psycopg2.extras import Json
        
        if hasattr(self, 'id') and self.id:
            # Update
            cols = []
            vals = []
            for k, v in self.__dict__.items():
                if k.startswith('_') or k == 'id': continue
                if k not in self.ALLOWED_COLUMNS: continue
                
                cols.append(f"{k} = %s")
                if isinstance(v, (dict, list)):
                    vals.append(Json(v))
                else:
                    vals.append(v)
            
            sql = f"UPDATE orders SET {', '.join(cols)} WHERE id = %s"
            vals.append(self.id)
            db.execute(sql, tuple(vals))
            db.commit()
        else:
            # Insert
            cols = []
            vals = []
            placeholders = []
            for k, v in self.__dict__.items():
                if k.startswith('_'): continue
                if k not in self.ALLOWED_COLUMNS: continue
                
                cols.append(k)
                
                if isinstance(v, (dict, list)):
                    vals.append(Json(v))
                else:
                    vals.append(v)
                    
                placeholders.append("%s")
            
            sql = f"INSERT INTO orders ({', '.join(cols)}) VALUES ({', '.join(placeholders)}) RETURNING id"
            row = db.execute(sql, tuple(vals)).fetchone()
            self.id = row['id']
            db.commit()


class AppEvent:
    ALLOWED_COLUMNS = (
        'id', 'event_type', 'source', 'user_id', 'property_id', 'session_id', 
        'qr_code', 'sign_asset_id', 'payload', 'occurred_at',
        # Added in migration 019/021
        'order_id', 'request_id', 'ip_hash', 'ua_hash',
        'event_uuid', 'received_at', 'schema_version', 'environment',
        'actor_type', 'actor_id', 'subject_type', 'subject_id', 'idempotency_key'
    )

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            if k in self.ALLOWED_COLUMNS:
                setattr(self, k, v)
    
    @classmethod
    def create(cls, **kwargs):
        """
        Create and save an event in one go.
        Normally handled by services/events.py via helper, but this allows direct usage.
        """
        db = get_db()
        from psycopg2.extras import Json
        
        cols = []
        vals = []
        placeholders = []
        
        for k, v in kwargs.items():
            if k == 'id' or k.startswith('_'): continue
            if k not in cls.ALLOWED_COLUMNS: continue
            
            cols.append(k)
            if k == 'payload' and isinstance(v, (dict, list)):
                vals.append(Json(v))
            else:
                vals.append(v)
            placeholders.append("%s")
            
        sql = f"INSERT INTO app_events ({', '.join(cols)}) VALUES ({', '.join(placeholders)}) RETURNING id"
        row = db.execute(sql, tuple(vals)).fetchone()
        db.commit()
        
        return cls(**kwargs, id=row['id'])

    @classmethod
    def get_by_property(cls, property_id, limit=50):
        db = get_db()
        rows = db.execute(
            "SELECT * FROM app_events WHERE property_id = %s ORDER BY occurred_at DESC LIMIT %s",
            (property_id, limit)
        ).fetchall()
        return [cls(**dict(r)) for r in rows]

class AgentAction:
    ALLOWED_COLUMNS = (
        'id', 'user_id', 'action_type', 'status', 'proposal', 'execution', 
        'feedback', 'policy_snapshot', 'input_event_refs', 'created_at', 'updated_at'
    )

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            if k in self.ALLOWED_COLUMNS:
                setattr(self, k, v)
    
    @classmethod
    def create(cls, **kwargs):
        db = get_db()
        from psycopg2.extras import Json
        
        cols = []
        vals = []
        placeholders = []
        
        for k, v in kwargs.items():
            if k == 'id' or k.startswith('_'): continue
            if k not in cls.ALLOWED_COLUMNS: continue
            
            cols.append(k)
            if k in ('proposal', 'execution', 'policy_snapshot', 'input_event_refs') and isinstance(v, (dict, list)):
                vals.append(Json(v))
            else:
                vals.append(v)
            placeholders.append("%s")
            
        sql = f"INSERT INTO agent_actions ({', '.join(cols)}) VALUES ({', '.join(placeholders)}) RETURNING id"
        row = db.execute(sql, tuple(vals)).fetchone()
        db.commit()
        
        return cls(**kwargs, id=row['id'])

    def save(self):
        db = get_db()
        from psycopg2.extras import Json
        
        if hasattr(self, 'id') and self.id:
            # Update
            cols = []
            vals = []
            for k, v in self.__dict__.items():
                if k.startswith('_') or k == 'id': continue
                if k not in self.ALLOWED_COLUMNS: continue
                
                cols.append(f"{k} = %s")
                if k in ('proposal', 'execution', 'policy_snapshot', 'input_event_refs') and isinstance(v, (dict, list)):
                    vals.append(Json(v))
                else:
                    vals.append(v)
            
            # Explicitly force updated_at=now() on save
            cols.append("updated_at = now()")
            
            sql = f"UPDATE agent_actions SET {', '.join(cols)} WHERE id = %s"
            vals.append(self.id)
            db.execute(sql, tuple(vals))
            db.commit()
    
    @classmethod
    def get(cls, action_id):
        db = get_db()
        row = db.execute("SELECT * FROM agent_actions WHERE id = %s", (action_id,)).fetchone()
        if not row: return None
        return cls(**dict(row))

# Mock db object for legacy imports (e.g. imports Order, db)
# This allows 'from models import db' to work, giving access to raw connection wrapper if needed
class DBProxy:
    @property
    def session(self):
        return self
    
    def add(self, obj):
        if hasattr(obj, 'save'):
            obj.save()
    
    def commit(self):
        get_db().commit()

    def execute(self, sql, params=None):
        """Delegates execute to the underlying raw connection (compatibility layer)."""
        return get_db().execute(sql, params)
        
    def cursor(self):
        return get_db().cursor()
        
db = DBProxy()
