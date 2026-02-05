import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

from database import get_db
from app import create_app

def apply_migration():
    app = create_app()
    with app.app_context():
        db = get_db()
        print("Applying migration 038 logic directly...")
        
        # 1. Update print_product
        res1 = db.execute("""
            UPDATE orders 
            SET print_product = REPLACE(print_product, 'listing_sign', 'yard_sign')
            WHERE print_product LIKE 'listing_sign%'
        """)
        print(f"Updated print_product count: {res1.rowcount}")
        
        # 2. Update order_type
        res2 = db.execute("""
            UPDATE orders 
            SET order_type = 'yard_sign'
            WHERE order_type = 'listing_sign'
        """)
        print(f"Updated order_type count: {res2.rowcount}")
        
        db.commit()
        print("Done.")

if __name__ == "__main__":
    apply_migration()
