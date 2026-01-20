"""
DEPRECATED: This PIL-based sign generator is no longer used.

The PDF generator (utils/pdf_generator.py) is now the source of truth for sign
rendering, and previews are derived from PDFs via utils/pdf_preview.py.

This file is kept for historical reference but should not be imported.
All sign generation should go through generate_pdf_sign() instead.

TODO: Remove this file after confirming no imports remain and tests pass.
"""
from PIL import Image, ImageDraw, ImageFont
import os
from config import SIGN_PATH
from constants import SIGN_SIZES, DEFAULT_SIGN_COLOR, DEFAULT_SIGN_SIZE

def generate_sign(address, beds, baths, sqft, price, agent_name, brokerage, agent_email, agent_phone, qr_path, agent_photo_path=None, sign_color=None, sign_size=None):
    """
    Generate a real estate sign with customizable color and size.
    
    Args:
        sign_color: Hex color for banner (e.g., '#1F6FEB')
        sign_size: Size preset key (e.g., '18x24')
    """
    # Default values
    if not sign_color:
        sign_color = DEFAULT_SIGN_COLOR
    if not sign_size:
        sign_size = DEFAULT_SIGN_SIZE
    
    # Get size configuration
    size_config = SIGN_SIZES.get(sign_size, SIGN_SIZES[DEFAULT_SIGN_SIZE])
    dpi = size_config['dpi']
    width = size_config['width_in'] * dpi
    height = size_config['height_in'] * dpi
    
    # Create canvas
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)

    # Calculate scale factor for fonts (relative to 18x24 @ 300 DPI = 5400x7200)
    base_width = 5400
    scale = width / base_width

    # Try to load a nice font, fallback to default if necessary
    try:
        font_path = os.path.join("static", "fonts", "Montserrat-Bold.ttf")
        
        # Scale fonts proportionally
        font_address = ImageFont.truetype(font_path, int(360 * scale))
        font_details = ImageFont.truetype(font_path, int(220 * scale))
        font_agent = ImageFont.truetype(font_path, int(170 * scale))
        font_price = ImageFont.truetype(font_path, int(700 * scale))
        font_banner_main = ImageFont.truetype(font_path, int(170 * scale))
        font_banner_sub = ImageFont.truetype(font_path, int(130 * scale))
    except IOError:
        print("Warning: Montserrat font not found, falling back to Arial/Default.")
        try:
            font_address = ImageFont.truetype("arial.ttf", int(360 * scale))
            font_details = ImageFont.truetype("arial.ttf", int(220 * scale))
            font_agent = ImageFont.truetype("arial.ttf", int(170 * scale))
            font_price = ImageFont.truetype("arial.ttf", int(700 * scale))
            font_banner_main = ImageFont.truetype("arial.ttf", int(170 * scale))
            font_banner_sub = ImageFont.truetype("arial.ttf", int(130 * scale))
        except IOError:
            font_address = ImageFont.load_default()
            font_details = ImageFont.load_default()
            font_agent = ImageFont.load_default()
            font_price = ImageFont.load_default()
            font_banner_main = ImageFont.load_default()
            font_banner_sub = ImageFont.load_default()

    # --- Colors ---
    COLOR_ORANGE = (212, 93, 18)  # For price
    COLOR_WHITE = (255, 255, 255)
    
    # Parse hex color for banner
    COLOR_BANNER = tuple(int(sign_color.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))

    # --- Layout ---
    
    # 1. Address & Details (Top) - scaled
    details_line = f"{address.upper()}"
    features_line = f"{beds} BEDS | {baths} BATHS"
    if sqft: features_line += f" | {sqft} SQ FT"
    
    draw.text((width // 2, int(360 * scale)), details_line, fill="black", anchor="mm", font=font_details)
    draw.text((width // 2, int(640 * scale)), features_line, fill="grey", anchor="mm", font=font_details)

    # 2. QR Code (Center) - scaled
    if os.path.exists(qr_path):
        qr_img = Image.open(qr_path)
        qr_size = int(3400 * scale)  # Proportional to canvas
        qr_img = qr_img.resize((qr_size, qr_size), Image.Resampling.LANCZOS)
        
        qr_x = (width - qr_size) // 2
        qr_y = int(900 * scale)
        img.paste(qr_img, (qr_x, qr_y))
    else:
        print(f"Error: QR path {qr_path} not found")

    # 3. Price (Below QR) - scaled
    if price:
        display_price = price if "$" in price else f"${price}"
        draw.text((width // 2, int(4900 * scale)), display_price, fill=COLOR_ORANGE, anchor="mm", font=font_price)

    # 4. Colored Banner (Bottom) - using custom color
    banner_height = int(1800 * scale)
    banner_top = height - banner_height
    draw.rectangle([0, banner_top, width, height], fill=COLOR_BANNER)

    agent_main = agent_name.upper()
    if brokerage:
        agent_main += f" | {brokerage.upper()}"
        
    agent_sub = f"{agent_email.lower()} | {agent_phone}"

    # If photo exists, layout with photo
    if agent_photo_path and os.path.exists(agent_photo_path):
        try:
            photo_img = Image.open(agent_photo_path)
            photo_max_size = int(1500 * scale)
            
            w, h = photo_img.size
            if w > h:
                new_w = photo_max_size
                new_h = int(h * (photo_max_size / w))
            else:
                new_h = photo_max_size
                new_w = int(w * (photo_max_size / h))
                
            photo_img = photo_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            
            gap = int(160 * scale)
            text_width = max(draw.textlength(agent_main, font=font_banner_main), 
                             draw.textlength(agent_sub, font=font_banner_sub))
            total_w = photo_img.width + gap + text_width
            
            start_x = (width - total_w) // 2
            photo_y = banner_top + (banner_height - photo_img.height) // 2
            img.paste(photo_img, (int(start_x), int(photo_y)))
            
            text_x = start_x + photo_img.width + gap
            draw.text((text_x, banner_top + int(700 * scale)), agent_main, fill=COLOR_WHITE, anchor="lm", font=font_banner_main)
            draw.text((text_x, banner_top + int(1140 * scale)), agent_sub, fill=COLOR_WHITE, anchor="lm", font=font_banner_sub)
            
        except Exception as e:
            print(f"Error processing agent photo: {e}")
            draw.text((width // 2, banner_top + int(700 * scale)), agent_main, fill=COLOR_WHITE, anchor="mm", font=font_banner_main)
            draw.text((width // 2, banner_top + int(1140 * scale)), agent_sub, fill=COLOR_WHITE, anchor="mm", font=font_banner_sub)
    else:
        # Standard Centered Layout
        draw.text((width // 2, banner_top + int(700 * scale)), agent_main, fill=COLOR_WHITE, anchor="mm", font=font_banner_main)
        draw.text((width // 2, banner_top + int(1140 * scale)), agent_sub, fill=COLOR_WHITE, anchor="mm", font=font_banner_sub)

    # Save
    filename = address.replace(" ", "_").replace(".", "").replace(",", "") + "_Sign.png"
    save_path = os.path.join(SIGN_PATH, filename)
    img.save(save_path)

    return save_path
