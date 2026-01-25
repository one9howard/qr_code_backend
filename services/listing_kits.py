
import os
import io
import zipfile
from datetime import datetime, timezone
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, inch
from PIL import Image, ImageDraw, ImageFont
from database import get_db
from utils.storage import get_storage
from config import BASE_URL

def create_or_get_kit(user_id, property_id):
    """
    Get existing kit or create a pending one.
    """
    db = get_db()
    
    # Check existence
    existing = db.execute(
        "SELECT * FROM listing_kits WHERE property_id = %s", 
        (property_id,)
    ).fetchone()
    
    if existing:
        return dict(existing)
        
    # Create
    cursor = db.execute(
        """
        INSERT INTO listing_kits (user_id, property_id, status)
        VALUES (%s, %s, 'pending')
        RETURNING id
        """,
        (user_id, property_id)
    )
    db.commit()
    kit_id = cursor.fetchone()['id']
    
    # Return full row (re-fetch to be safe/consistent)
    return db.execute("SELECT * FROM listing_kits WHERE id = %s", (kit_id,)).fetchone()

def generate_kit(kit_id):
    """
    Generate all assets for a listing kit, zip them, and upload.
    Updates DB status.
    """
    db = get_db()
    kit = db.execute("SELECT * FROM listing_kits WHERE id = %s", (kit_id,)).fetchone()
    if not kit:
        return
        
    prop = db.execute(
        """
        SELECT p.*, a.name as agent_name, a.brokerage, a.email as agent_email, a.phone as agent_phone,
               u.email as user_email, u.id as user_id, 
               a.photo_filename, a.logo_filename
        FROM properties p
        JOIN agents a ON p.agent_id = a.id
        JOIN users u ON a.user_id = u.id
        WHERE p.id = %s
        """, 
        (kit['property_id'],)
    ).fetchone()
    
    if not prop:
        db.execute("UPDATE listing_kits SET status='failed', last_error='Property not found' WHERE id=%s", (kit_id,))
        db.commit()
        return

    try:
        storage = get_storage()
        prop_id = kit['property_id']
        prefix = f"kits/property_{prop_id}"
        
        # 1. Generate Flyer PDF
        flyer_buffer = _generate_flyer(prop)
        flyer_key = f"{prefix}/flyer.pdf"
        storage.put_file(flyer_buffer, flyer_key, "application/pdf")
        
        # 2. Generate Social Square
        square_buffer = _generate_social_square(prop)
        square_key = f"{prefix}/social_square.png"
        storage.put_file(square_buffer, square_key, "image/png")
        
        # 3. Generate Social Story
        story_buffer = _generate_social_story(prop)
        story_key = f"{prefix}/social_story.png"
        storage.put_file(story_buffer, story_key, "image/png")
        
        # 4. Include Sign PDF (From Order or Generate)
        sign_pdf_buffer = None
        
        # Try to find existing order
        order = db.execute(
            """
            SELECT sign_pdf_path FROM orders 
            WHERE property_id = %s AND order_type IN ('listing_sign', 'sign') AND sign_pdf_path IS NOT NULL
            ORDER BY created_at DESC LIMIT 1
            """,
            (prop_id,)
        ).fetchone()
        
        if order and order['sign_pdf_path'] and storage.exists(order['sign_pdf_path']):
             try:
                 sign_pdf_buffer = storage.get_file(order['sign_pdf_path'])
             except: pass

        if not sign_pdf_buffer:
            # Generate deterministically
            try:
                from utils.pdf_generator import generate_pdf_sign
                from config import BASE_URL
                
                # Gather args
                full_url = f"{BASE_URL}/r/{prop['qr_code']}" if prop['qr_code'] else f"{BASE_URL}/p/{prop['slug']}"
                
                # Generate to local temp path (order_id=None trigger)
                temp_pdf_path = generate_pdf_sign(
                     address=prop['address'],
                     beds=prop['beds'],
                     baths=prop['baths'],
                     sqft=prop['sqft'],
                     price=prop['price'],
                     agent_name=prop['agent_name'],
                     brokerage=prop['brokerage'],
                     agent_email=prop['agent_email'],
                     agent_phone=prop['agent_phone'],
                     qr_key=None, 
                     agent_photo_key=prop.get('photo_filename'), 
                     sign_color=None, # Default
                     sign_size=None, # Default
                     order_id=None, # LEGACY MODE -> Returns local path
                     qr_value=full_url,
                     user_id=prop['user_id'],
                     logo_key=prop.get('logo_filename')
                )
                
                # Read into buffer
                if temp_pdf_path and os.path.exists(temp_pdf_path):
                    with open(temp_pdf_path, 'rb') as f:
                        sign_pdf_buffer = io.BytesIO(f.read())
                    try:
                        os.remove(temp_pdf_path)
                    except: pass
                
            except Exception as e:
                print(f"Failed to generate sign PDF for kit: {e}")

        # 4. Create ZIP
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Add generated assets
            flyer_buffer.seek(0)
            zf.writestr("flyer.pdf", flyer_buffer.read())
            
            square_buffer.seek(0)
            zf.writestr("social_square.png", square_buffer.read())
            
            story_buffer.seek(0)
            zf.writestr("social_story.png", story_buffer.read())
            
            if sign_pdf_buffer:
                sign_pdf_buffer.seek(0)
                zf.writestr("sign.pdf", sign_pdf_buffer.read())
        
        zip_buffer.seek(0)
        zip_key = f"{prefix}/kit.zip"
        storage.put_file(zip_buffer, zip_key, "application/zip")
        
        # Update DB
        db.execute(
            """
            UPDATE listing_kits 
            SET status='ready', 
                kit_zip_path=%s, 
                flyer_pdf_path=%s, 
                social_square_path=%s, 
                social_story_path=%s,
                updated_at=now(),
                last_error=NULL
            WHERE id=%s
            """,
            (zip_key, flyer_key, square_key, story_key, kit_id)
        )
        db.commit()
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        db.execute(
            "UPDATE listing_kits SET status='failed', last_error=%s, updated_at=now() WHERE id=%s", 
            (str(e), kit_id)
        )
        db.commit()

def _generate_flyer(prop):
    """Generate simple professional flyer PDF."""
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    
    # Simple Layout
    margin = 50
    
    # Address
    c.setFont("Helvetica-Bold", 24)
    c.drawString(margin, height - 80, (prop['address'] or "Address TBD").upper())
    
    # Details
    c.setFont("Helvetica", 14)
    details = []
    if prop['beds']: details.append(f"{prop['beds']} Beds")
    if prop['baths']: details.append(f"{prop['baths']} Baths")
    if prop['sqft']: details.append(f"{prop['sqft']} Sq Ft")
    
    c.drawString(margin, height - 110, " | ".join(details))
    
    # Price
    if prop['price']:
        c.setFont("Helvetica-Bold", 18)
        c.drawString(margin, height - 140, f"${prop['price']}")
        
    # QR Code
    qr_url = f"{BASE_URL}/r/{prop['qr_code']}" if prop['qr_code'] else f"{BASE_URL}/p/{prop['slug']}"
    from utils.pdf_generator import draw_qr
    
    # Draw QR at bottom right
    qr_size = 150
    qr_x = width - margin - qr_size
    qr_y = margin
    draw_qr(c, qr_url, x=qr_x, y=qr_y, size=qr_size, user_id=prop.get('user_id'))
    
    # Footer: Agent Info
    c.setFont("Helvetica-Bold", 12)
    c.drawString(margin, margin + 40, (prop['agent_name'] or "Agent").upper())
    if prop['brokerage']:
        c.setFont("Helvetica", 12)
        c.drawString(margin, margin + 25, prop['brokerage'].upper())
    
    c.setFont("Helvetica", 10)
    c.drawString(margin, margin, f"{prop['agent_email']} | {prop['agent_phone']}")
    
    c.save()
    buffer.seek(0)
    return buffer

def _generate_social_square(prop):
    """Generate 1080x1080 PNG."""
    return _generate_image(prop, 1080, 1080)

def _generate_social_story(prop):
    """Generate 1080x1920 PNG."""
    return _generate_image(prop, 1080, 1920)

def _generate_image(prop, w, h):
    """Helper for image generation."""
    img = Image.new('RGB', (w, h), color='#1a1a2e') # Dark blue bg
    d = ImageDraw.Draw(img)
    
    # Basic text (Pillow default font is limited, but works for MVP)
    # Ideally load a TTF, but for MVP/No-External-Service constraints, default might be safe
    # or rely on system fonts? Pillow default font is tiny.
    # Let's try to load a basic font or generic.
    try:
        # Try typical linux path or font
        font_large = ImageFont.truetype("arial.ttf", 60)
        font_med = ImageFont.truetype("arial.ttf", 40)
    except IOError:
        # Fallback to default (ugly but works)
        font_large = ImageFont.load_default()
        font_med =  ImageFont.load_default()

    # Address Center
    text = (prop['address'] or "New Listing").upper()
    
    # Simple centering logic
    try:
        # Pillow >= 10
        bbox = d.textbbox((0, 0), text, font=font_large)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
    except AttributeError:
        # Pillow < 10
        text_w, text_h = d.textsize(text, font=font_large)
        
    d.text(((w - text_w)/2, h/2 - 100), text, fill="white", font=font_large)
    
    # Details
    details = []
    if prop['beds']: details.append(f"{prop['beds']} BEDS")
    if prop['baths']: details.append(f"{prop['baths']} BATHS")
    subtext = " | ".join(details)
    
    if subtext:
        try:
             bbox = d.textbbox((0, 0), subtext, font=font_med)
             sub_w = bbox[2] - bbox[0]
        except AttributeError:
             sub_w, _ = d.textsize(subtext, font=font_med)
             
        d.text(((w - sub_w)/2, h/2), subtext, fill="#cccccc", font=font_med)

    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    return buffer
