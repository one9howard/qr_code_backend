
import os
import io
import zipfile
from datetime import datetime, timezone
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, inch
from PIL import Image, ImageDraw, ImageFont
from database import get_db
from utils.storage import get_storage
from config import PUBLIC_BASE_URL
from services.printing.yard_sign import generate_yard_sign_pdf

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
        VALUES (%s, %s, 'queued')
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
        
    # Transition to generating
    db.execute("UPDATE listing_kits SET status='generating' WHERE id=%s", (kit_id,))
    db.commit()
    
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
            WHERE property_id = %s AND order_type IN ('yard_sign', 'sign') AND sign_pdf_path IS NOT NULL
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
                # from utils.pdf_generator import generate_pdf_sign (Moved to top)
                
                # Gather args
                full_url = f"{PUBLIC_BASE_URL}/r/{prop['qr_code']}" if prop['qr_code'] else f"{PUBLIC_BASE_URL}/p/{prop['slug']}"
                
                # Generate using unified path
                temp_pdf_key = f"{prefix}/temp_sign.pdf"
                
                # Mock order structure for unified generator
                mock_order = {
                    'id': None,
                    'property_id': prop['id'],
                    'user_id': prop['user_id'],
                    'sign_color': '#0077ff', # Default/Brand
                    'sign_size': '18x24',
                    'layout_id': 'listing_modern_round'
                }
                
                generated_key = generate_yard_sign_pdf(
                     mock_order,
                     output_key=temp_pdf_key
                )
                
                # key return is guaranteed if legacy_mode=False
                sign_pdf_buffer = storage.get_file(generated_key)
                
                # Cleanup temp key from S3 to keep bucket clean
                try:
                    storage.delete(generated_key)
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

# Additional imports for modern layout
import services.printing.layout_utils as lu
from reportlab.lib.colors import HexColor

NAVY_COLOR = '#0f172a'
WHITE_COLOR = '#ffffff'
GRAY_COLOR = '#64748b'

def _generate_flyer(prop):
    """
    Generate Modern Professional Flyer.
    Style: Navy Header, Clean White Body, Large QR.
    """
    # Register Fonts
    lu.register_fonts()
    
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    
    # --- 1. Header (Navy) ---
    header_h = 160
    c.setFillColor(HexColor(NAVY_COLOR))
    c.rect(0, height - header_h, width, header_h, fill=1, stroke=0)
    
    # Address (White, Centered in Header)
    c.setFillColor(HexColor(WHITE_COLOR))
    
    # Address Line 1
    addr_text = (prop['address'] or "Address TBD").upper()
    # Fit text
    fs = lu.fit_text_one_line(c, addr_text, lu.FONT_BOLD, width * 0.8, 48, 24)
    c.setFont(lu.FONT_BOLD, fs)
    c.drawCentredString(width/2, height - (header_h/2) + 10, addr_text)
    
    # "FOR SALE" or Status above address
    c.setFont(lu.FONT_MED, 18)
    c.setFillColor(HexColor('#94a3b8')) # Light Slate
    c.drawCentredString(width/2, height - (header_h/2) + fs, "JUST LISTED")

    # --- 2. Body Content ---
    cursor_y = height - header_h - 60
    
    # Price (Large, Navy)
    if prop['price']:
        price_text = f"${prop['price']:,}" if isinstance(prop['price'], (int, float)) else str(prop['price'])
        if '$' not in price_text: price_text = f"${price_text}"
        
        c.setFillColor(HexColor(NAVY_COLOR))
        c.setFont(lu.FONT_BOLD, 60)
        c.drawCentredString(width/2, cursor_y, price_text)
        cursor_y -= 80
        
    # Features (Row)
    c.setFillColor(HexColor(GRAY_COLOR))
    c.setFont(lu.FONT_MED, 24)
    
    details = []
    if prop['beds']: details.append(f"{prop['beds']} Beds")
    if prop['baths']: details.append(f"{prop['baths']} Baths")
    if prop['sqft']: details.append(f"{prop['sqft']} Sq Ft")
    
    details_text = "  |  ".join(details)
    c.drawCentredString(width/2, cursor_y, details_text)
    
    # --- 3. QR Code (Central Feature) ---
    # Large Vector QR
    qr_size = 220
    qr_y = cursor_y - 80 - qr_size
    qr_x = (width - qr_size) / 2
    
    qr_url = f"{PUBLIC_BASE_URL}/r/{prop['qr_code']}" if prop['qr_code'] else f"{PUBLIC_BASE_URL}/p/{prop['slug']}"
    from utils.pdf_generator import draw_qr
    
    draw_qr(c, qr_url, x=qr_x, y=qr_y, size=qr_size, user_id=prop.get('user_id'), ecc_level="H")
    
    # CTA under QR
    c.setFillColor(HexColor(NAVY_COLOR))
    c.setFont(lu.FONT_BOLD, 20)
    c.drawCentredString(width/2, qr_y - 30, "SCAN FOR PHOTOS & DETAILS")
    
    # --- 4. Footer (Agent Identity) ---
    # Draw line separator
    footer_y = 120
    c.setStrokeColor(HexColor('#e2e8f0'))
    c.setLineWidth(2)
    c.line(50, footer_y, width-50, footer_y)
    
    # Agent Name
    text_x = width / 2
    cursor_y = footer_y - 40
    
    c.setFillColor(HexColor(NAVY_COLOR))
    c.setFont(lu.FONT_BOLD, 22)
    c.drawCentredString(text_x, cursor_y, (prop['agent_name'] or "Agent").upper())
    
    # Brokerage
    if prop['brokerage']:
        cursor_y -= 25
        c.setFont(lu.FONT_MED, 16)
        c.setFillColor(HexColor(GRAY_COLOR))
        c.drawCentredString(text_x, cursor_y, prop['brokerage'].upper())
        
    # Contact
    cursor_y -= 25
    c.setFont(lu.FONT_MED, 14)
    contact_line = f"{prop['agent_phone']}  |  {prop['agent_email']}"
    c.drawCentredString(text_x, cursor_y, contact_line)

    c.showPage()
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
        # Use Inter font (open source, already shipped)
        font_path = os.path.join(os.path.dirname(__file__), '..', 'static', 'fonts', 'Inter-Regular.ttf')
        font_large = ImageFont.truetype(font_path, 60)
        font_med = ImageFont.truetype(font_path, 40)
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
