#!/usr/bin/env python3
"""
Render Sample Signs for Visual QA.

This script renders sample signs in all supported sizes for visual regression testing.
Outputs to static/generated/debug_samples/

Usage:
    python scripts/render_samples.py
    python scripts/render_samples.py --order-id 123
"""
import os
import sys
import argparse

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import STATIC_DIR, QR_PATH, UPLOAD_DIR
from constants import SIGN_SIZES, DEFAULT_SIGN_COLOR
from utils.pdf_generator import generate_pdf_sign
from utils.pdf_preview import render_pdf_to_web_preview
from database import get_db, get_agent_data_for_order


# Sample data for standalone rendering
SAMPLE_DATA = {
    'address': '123 Sample Street, Demo City',
    'beds': '4',
    'baths': '3',
    'sqft': '2,500',
    'price': '$899,000',
    'agent_name': 'Jane Agent',
    'brokerage': 'Demo Realty',
    'agent_email': 'jane@demorealty.com',
    'agent_phone': '(555) 123-4567',
}


def get_output_dir():
    """Get or create the debug samples output directory."""
    output_dir = os.path.join(STATIC_DIR, "generated", "debug_samples")
    os.makedirs(output_dir, exist_ok=True)
    return output_dir


def get_sample_qr_path():
    """Get a sample QR code path, or generate a placeholder."""
    # Look for any existing QR code
    if os.path.exists(QR_PATH):
        for f in os.listdir(QR_PATH):
            if f.endswith('.png'):
                return os.path.join(QR_PATH, f)
    
    # Create a simple placeholder
    placeholder_path = os.path.join(get_output_dir(), "sample_qr.png")
    if not os.path.exists(placeholder_path):
        try:
            from PIL import Image
            img = Image.new('RGB', (400, 400), 'white')
            img.save(placeholder_path)
        except ImportError:
            print("Warning: PIL not available for placeholder QR")
            return None
    return placeholder_path


def render_all_sizes(order_id=None, agent_photo_path=None):
    """
    Render sample signs in all supported sizes.
    
    Args:
        order_id: Optional order ID to fetch real data from
        agent_photo_path: Optional path to agent photo
    """
    output_dir = get_output_dir()
    qr_path = get_sample_qr_path()
    
    if not qr_path:
        print("Error: No QR code available for rendering")
        return
    
    # Get data from order if provided
    if order_id:
        from flask import Flask
        from config import SECRET_KEY
        
        app = Flask(__name__)
        app.config['SECRET_KEY'] = SECRET_KEY
        
        with app.app_context():
            # No init_db needed for get_db in refactored database.py usually, 
            # but ensuring context is enough if get_db uses g.
            db = get_db()
            
            # Using %s now
            order = db.execute("SELECT * FROM orders WHERE id = %s", (order_id,)).fetchone()
            if not order:
                print(f"Error: Order {order_id} not found")
                return
            
            prop = db.execute("SELECT * FROM properties WHERE id = %s", (order['property_id'],)).fetchone()
            agent = get_agent_data_for_order(order_id)
            
            if not agent:
                agent = db.execute(
                    "SELECT * FROM agents WHERE id = %s",
                    (prop['agent_id'],)
                ).fetchone()
                agent = dict(agent) if agent else SAMPLE_DATA
            
            data = {
                'address': prop['address'],
                'beds': prop['beds'],
                'baths': prop['baths'],
                'sqft': prop.get('sqft', ''),
                'price': prop.get('price', ''),
                'agent_name': agent['name'],
                'brokerage': agent['brokerage'],
                'agent_email': agent['email'],
                'agent_phone': agent.get('phone', ''),
            }
            sign_color = order.get('sign_color', DEFAULT_SIGN_COLOR)
            
            if agent.get('photo_filename'):
                agent_photo_path = os.path.join(UPLOAD_DIR, agent['photo_filename'])
    else:
        data = SAMPLE_DATA
        sign_color = DEFAULT_SIGN_COLOR
    
    print(f"Output directory: {output_dir}")
    print(f"Using QR: {qr_path}")
    print(f"Agent photo: {agent_photo_path or 'None'}")
    print("-" * 50)
    
    for size_key in SIGN_SIZES.keys():
        print(f"Rendering {size_key}...", end=" ")
        
        try:
            # Generate PDF
            pdf_path = generate_pdf_sign(
                address=data['address'],
                beds=data['beds'],
                baths=data['baths'],
                sqft=data.get('sqft', ''),
                price=data.get('price', ''),
                agent_name=data['agent_name'],
                brokerage=data['brokerage'],
                agent_email=data['agent_email'],
                agent_phone=data.get('agent_phone', ''),
                qr_path=qr_path,
                agent_photo_path=agent_photo_path,
                sign_color=sign_color,
                sign_size=size_key,
            )
            
            # Move PDF to output directory
            pdf_basename = f"sample_{size_key}.pdf"
            output_pdf = os.path.join(output_dir, pdf_basename)
            if pdf_path != output_pdf:
                import shutil
                shutil.copy(pdf_path, output_pdf)
            
            # Generate preview
            preview_path = render_pdf_to_web_preview(
                pdf_path=output_pdf,
                sign_size=size_key,
            )
            
            # Move preview to output directory
            preview_basename = f"sample_{size_key}_preview.webp"
            output_preview = os.path.join(output_dir, preview_basename)
            if preview_path != output_preview:
                import shutil
                shutil.copy(preview_path, output_preview)
            
            print(f"✓ PDF: {pdf_basename}, Preview: {preview_basename}")
            
        except Exception as e:
            print(f"✗ Error: {e}")
    
    print("-" * 50)
    print(f"Done! View samples in: {output_dir}")


def main():
    parser = argparse.ArgumentParser(description="Render sample signs for QA")
    parser.add_argument(
        '--order-id', '-o',
        type=int,
        help='Order ID to use for data (uses sample data if not provided)'
    )
    parser.add_argument(
        '--photo', '-p',
        type=str,
        help='Path to agent photo'
    )
    
    args = parser.parse_args()
    
    render_all_sizes(
        order_id=args.order_id,
        agent_photo_path=args.photo
    )


if __name__ == "__main__":
    main()
