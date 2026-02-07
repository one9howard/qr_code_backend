"""
Test entity factories for InSite Signs.

Centralizes test data creation to avoid schema drift from NOT NULL columns.
All entity creation should go through these factories.
"""
from werkzeug.security import generate_password_hash
from datetime import datetime, timezone
import uuid


class UserFactory:
    """Factory for creating test users."""
    
    DEFAULT_PASSWORD = 'TestPassword123!'
    
    @classmethod
    def create(cls, db_session, **kwargs):
        """
        Create a user with sensible defaults.
        
        Args:
            db_session: Database connection
            **kwargs: Override any field
            
        Returns:
            int: Created user ID
        """
        defaults = {
            'email': f'test-{uuid.uuid4().hex[:8]}@example.com',
            'password_hash': generate_password_hash(cls.DEFAULT_PASSWORD),
            'is_admin': False,
            'is_verified': True,
            'subscription_status': 'free',
        }
        defaults.update(kwargs)
        
        cursor = db_session.cursor()
        cursor.execute(
            """
            INSERT INTO users (email, password_hash, is_admin, is_verified, subscription_status)
            VALUES (%(email)s, %(password_hash)s, %(is_admin)s, %(is_verified)s, %(subscription_status)s)
            RETURNING id
            """,
            defaults
        )
        user_id = cursor.fetchone()['id']
        db_session.commit()
        return user_id


class AgentFactory:
    """Factory for creating test agents."""
    
    @classmethod
    def create(cls, db_session, user_id, **kwargs):
        """
        Create an agent with sensible defaults.
        
        Args:
            db_session: Database connection
            user_id: Owner user ID
            **kwargs: Override any field
            
        Returns:
            int: Created agent ID
        """
        defaults = {
            'user_id': user_id,
            'name': f'Test Agent {uuid.uuid4().hex[:6]}',
            'email': f'agent-{uuid.uuid4().hex[:8]}@example.com',
            'phone': '555-0100',
            'brokerage': 'Test Brokerage',
        }
        defaults.update(kwargs)
        
        cursor = db_session.cursor()
        cursor.execute(
            """
            INSERT INTO agents (user_id, name, email, phone, brokerage)
            VALUES (%(user_id)s, %(name)s, %(email)s, %(phone)s, %(brokerage)s)
            RETURNING id
            """,
            defaults
        )
        agent_id = cursor.fetchone()['id']
        db_session.commit()
        return agent_id


class PropertyFactory:
    """Factory for creating test properties."""
    
    @classmethod
    def create(cls, db_session, user_id, agent_id=None, **kwargs):
        """
        Create a property with sensible defaults.
        
        Args:
            db_session: Database connection
            user_id: Owner user ID
            agent_id: Optional agent ID
            **kwargs: Override any field
            
        Returns:
            int: Created property ID
        """
        defaults = {
            'user_id': user_id,
            'agent_id': agent_id,
            'address': f'{uuid.uuid4().hex[:4]} Test Street',
            'city': 'Test City',
            'state': 'TX',
            'zip_code': '12345',
            'price': 250000,
            'bedrooms': 3,
            'bathrooms': 2.0,
            'sqft': 1500,
            'qr_code': uuid.uuid4().hex[:8],
        }
        defaults.update(kwargs)
        
        cursor = db_session.cursor()
        cursor.execute(
            """
            INSERT INTO properties (user_id, agent_id, address, city, state, zip_code, 
                                    price, bedrooms, bathrooms, sqft, qr_code)
            VALUES (%(user_id)s, %(agent_id)s, %(address)s, %(city)s, %(state)s, %(zip_code)s,
                    %(price)s, %(bedrooms)s, %(bathrooms)s, %(sqft)s, %(qr_code)s)
            RETURNING id
            """,
            defaults
        )
        property_id = cursor.fetchone()['id']
        db_session.commit()
        return property_id


class OrderFactory:
    """Factory for creating test orders."""
    
    @classmethod
    def create(cls, db_session, user_id, **kwargs):
        """
        Create an order with sensible defaults.
        
        Args:
            db_session: Database connection
            user_id: Owner user ID
            **kwargs: Override any field
            
        Returns:
            int: Created order ID
        """
        defaults = {
            'user_id': user_id,
            'status': 'pending',
            'order_type': 'smartsign',
            'amount_total': 4999,  # $49.99 in cents
        }
        defaults.update(kwargs)
        
        cursor = db_session.cursor()
        cursor.execute(
            """
            INSERT INTO orders (user_id, status, order_type, amount_total)
            VALUES (%(user_id)s, %(status)s, %(order_type)s, %(amount_total)s)
            RETURNING id
            """,
            defaults
        )
        order_id = cursor.fetchone()['id']
        db_session.commit()
        return order_id
