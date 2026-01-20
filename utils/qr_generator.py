import qrcode
import io
from utils.storage import get_storage

def generate_qr(url, filename_slug):
    """
    Generate a QR code and save it to storage.
    
    Args:
        url: The content of the QR
        filename_slug: The filename base (usually the shortcode)
        
    Returns:
        str: The storage key of the generated QR code
    """
    # Ensure filename ends in .png
    if not filename_slug.lower().endswith(".png"):
        filename_slug += ".png"
        
    # Standardize folder
    key = f"qr/{filename_slug}"

    qr = qrcode.QRCode(
        version=4,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=12,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    
    # Save to memory
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)
    
    # Upload to storage
    storage = get_storage()
    storage.put_file(img_byte_arr, key, content_type="image/png")

    return key
