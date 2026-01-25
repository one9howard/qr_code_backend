
import logging
import io
import uuid
from PIL import Image, ImageOps
from flask import current_app
from database import get_db
from utils.storage import get_storage
from datetime import datetime, timezone
import config

logger = logging.getLogger(__name__)

MAX_LOGO_SIZE = 5 * 1024 * 1024  # 5 MB

def validate_and_normalize_logo(file_bytes: bytes) -> tuple[bytes, bytes]:
    """
    Validate and normalize a logo image.
    
    Returns:
        tuple(original_png_bytes, normalized_512_bytes)
    """
    if len(file_bytes) > MAX_LOGO_SIZE:
        raise ValueError("Image too large (max 5MB)")

    try:
        # Load image from bytes
        img = Image.open(io.BytesIO(file_bytes))
        
        # Security: Decompression bomb check (max 25MP)
        if img.width * img.height > 25_000_000:
            raise ValueError("Image dimensions too large (max 25MP)")

        # Normalize EXIF orientation
        img = ImageOps.exif_transpose(img)

        # Convert to RGBA
        img = img.convert('RGBA')
        
        # 1. Generate "Original" (Transposed, RGBA, PNG)
        # We re-encode to PNG to scrub metadata and ensure safety
        orig_buffer = io.BytesIO()
        img.save(orig_buffer, format='PNG')
        original_png = orig_buffer.getvalue()
        
        # 2. Generate "Normalized" (512x512 contained)
        target_size = (512, 512)
        canvas = Image.new('RGBA', target_size, (255, 255, 255, 0))
        
        # Resize thumbnail
        img.thumbnail(target_size, Image.Resampling.LANCZOS)
        
        # Center image
        offset_x = (target_size[0] - img.width) // 2
        offset_y = (target_size[1] - img.height) // 2
        
        canvas.paste(img, (offset_x, offset_y))
        
        norm_buffer = io.BytesIO()
        canvas.save(norm_buffer, format='PNG')
        normalized_png = norm_buffer.getvalue()
        
        return original_png, normalized_png
        
    except Exception as e:
        logger.warning(f"Logo validation failed: {str(e)}")
        if "too large" in str(e):
            raise e
        raise ValueError("Invalid image file.")

def save_qr_logo(user_id: int, file_storage) -> dict:
    """Save a new QR logo for a user."""
    # 1. Read bytes
    if hasattr(file_storage, 'read'):
        file_storage.seek(0)
        file_bytes = file_storage.read()
    else:
        file_bytes = file_storage
        
    # 2. Validate & Normalize
    original_png, normalized_png = validate_and_normalize_logo(file_bytes)
    
    # 3. Generate Keys (using uuid for uniqueness)
    file_id = str(uuid.uuid4())
    original_key = f"branding/qr_logo/original/{user_id}/{file_id}.png"
    normalized_key = f"branding/qr_logo/normalized/{user_id}/{file_id}.png"
    
    # 4. Store
    storage = get_storage()
    storage.put_file(original_png, original_key, content_type="image/png")
    storage.put_file(normalized_png, normalized_key, content_type="image/png")
    
    # 5. Update DB
    db = get_db()
    db.execute("""
        UPDATE users 
        SET qr_logo_original_key = %s,
            qr_logo_normalized_key = %s,
            qr_logo_updated_at = NOW()
        WHERE id = %s
    """, (original_key, normalized_key, user_id))
    db.commit()
    
    return {
        "original_key": original_key,
        "normalized_key": normalized_key
    }

def delete_qr_logo(user_id: int) -> None:
    """Delete QR logo assets and clear DB fields (Idempotent)."""
    db = get_db()
    
    # Get current keys to delete
    row = db.execute("SELECT qr_logo_original_key, qr_logo_normalized_key FROM users WHERE id = %s", (user_id,)).fetchone()
    if not row:
        return
        
    keys = [row['qr_logo_original_key'], row['qr_logo_normalized_key']]
    
    # Clear DB first
    db.execute("""
        UPDATE users 
        SET qr_logo_original_key = NULL,
            qr_logo_normalized_key = NULL,
            use_qr_logo = FALSE,
            qr_logo_updated_at = NULL
        WHERE id = %s
    """, (user_id,))
    db.commit()
    
    # Delete from storage (Idempotent)
    storage = get_storage()
    for key in keys:
        if key:
            try:
                if storage.exists(key):
                    storage.delete(key)
            except Exception as e:
                # Log but do not fail
                logger.warning(f"Failed to delete logo key {key}: {e}")

def set_use_qr_logo(user_id: int, enabled: bool) -> None:
    """Toggle usage of QR logo."""
    db = get_db()
    db.execute("UPDATE users SET use_qr_logo = %s WHERE id = %s", (enabled, user_id))
    db.commit()

def get_user_qr_logo_bytes(user_id: int) -> bytes | None:
    """
    Get the normalized logo bytes for a user IF enabled globally and per-user.
    
    Returns:
        bytes: The PNG bytes of the logo, or None if disabled/missing.
    """
    # 1. Global Flag
    if not config.ENABLE_QR_LOGO:
        return None
        
    # 2. User Toggle & Key
    db = get_db()
    user = db.execute(
        "SELECT use_qr_logo, qr_logo_normalized_key FROM users WHERE id = %s", 
        (user_id,)
    ).fetchone()
    
    if not user or not user['use_qr_logo'] or not user['qr_logo_normalized_key']:
        return None
        
    # 3. Retrieve Bytes
    storage = get_storage()
    try:
        file_obj = storage.get_file(user['qr_logo_normalized_key'])
        return file_obj.getvalue()
    except Exception as e:
        logger.error(f"Failed to retrieve logo for user {user_id}: {e}")
        return None
