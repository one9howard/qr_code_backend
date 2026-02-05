#!/usr/bin/env python
"""
Smoke test for listing sign PDF generation.

Usage:
    ORDER_ID=<id> python scripts/smoke_listing_pdf.py

Loads a real order row from the database and generates both PDF and preview.
"""
import os
import sys

# Fix import path for running from repo root
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

def main():
    order_id = os.environ.get("ORDER_ID")
    if not order_id:
        print("ERROR: ORDER_ID environment variable is required.")
        print("Usage: ORDER_ID=<id> python scripts/smoke_listing_pdf.py")
        return 1
    
    try:
        order_id = int(order_id)
    except ValueError:
        print(f"ERROR: ORDER_ID must be an integer, got: {order_id}")
        return 1
    
    # Create Flask app context for database access
    from app import create_app
    app = create_app()
    
    with app.app_context():
        # Load order from database
        from database import get_db
        db = get_db()
        
        order_row = db.execute("SELECT * FROM orders WHERE id = %s", (order_id,)).fetchone()
        if not order_row:
            print(f"ERROR: Order {order_id} not found in database.")
            return 1
        
        # Convert to dict
        if hasattr(order_row, '_asdict'):
            order_row = order_row._asdict()
        elif not isinstance(order_row, dict):
            order_row = dict(order_row)
        
        print(f"Loaded order: id={order_id}, type={order_row.get('order_type')}, size={order_row.get('print_size')}")
        
        # Generate PDF
        from services.printing.listing_sign import generate_listing_sign_pdf_from_order_row
        pdf_key = generate_listing_sign_pdf_from_order_row(order_row, db=db)
        print(f"OK listing pdf generated: {pdf_key}")
        
        # Generate preview
        from utils.pdf_preview import render_pdf_to_web_preview
        preview_key = render_pdf_to_web_preview(
            pdf_key=pdf_key,
            order_id=order_id,
            sign_size=order_row.get('print_size') or order_row.get('sign_size') or '18x24',
        )
        print(f"OK preview generated: {preview_key}")
        
        return 0

if __name__ == "__main__":
    sys.exit(main())
