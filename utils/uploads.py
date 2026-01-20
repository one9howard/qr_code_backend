"""
File upload security and handling utilities.
Provides validation, sanitization, and secure storage for uploaded files.
"""
import os
import uuid
import io
from werkzeug.utils import secure_filename
from PIL import Image
from utils.storage import get_storage

# Allowed file extensions for image uploads
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}

def allowed_file(filename):
    """Check if filename has an allowed extension."""
    if not filename:
        return False
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_extension_from_filename(filename):
    """Safely extract file extension from filename."""
    if not filename or '.' not in filename:
        return ''
    ext = filename.rsplit('.', 1)[1].lower()
    if ext in ALLOWED_EXTENSIONS:
        return f'.{ext}'
    return ''

def save_image_upload(file_storage, folder, base_name, validate_image=True):
    """
    Save uploaded file to the configured storage backend.
    
    Args:
        file_storage: FileStorage object from Flask request.files
        folder: Relative folder path (e.g. 'uploads/properties')
        base_name: Base name for file
        validate_image: If True, validate image content
        
    Returns:
        str: The storage key (relative path including filename)
    """
    if not file_storage or not file_storage.filename:
        raise ValueError("No file provided")
    
    # Validate extension
    if not allowed_file(file_storage.filename):
        raise ValueError(f"File type not allowed. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}")
    
    # Read file into memory for validation and size check
    # We do not rely on filesystem temp files to avoid ephemeral storage issues (though temp is usually fine)
    # 10MB limit is manageable in RAM
    file_bytes = file_storage.read()
    file_size = len(file_bytes)
    
    MAX_FILE_SIZE = 16 * 1024 * 1024  # 16MB (Matching config)
    if file_size > MAX_FILE_SIZE:
        raise ValueError(f"File too large. Maximum size is 16MB, got {file_size / 1024 / 1024:.1f}MB")
    
    # Determine extension
    ext = get_extension_from_filename(file_storage.filename)
    if not ext:
        raise ValueError("Invalid file extension")
    
    # Validate image content
    if validate_image:
        try:
            # Validate using PIL from memory
            with Image.open(io.BytesIO(file_bytes)) as img:
                img.verify()
                
            # Re-open to confirm format or valid
            # (verify consumes the stream in some PIL versions, safer to just trust verify() or re-open if needed later)
        except Exception as e:
            raise ValueError(f"Invalid image file: {str(e)}")

    # Generate unique filename
    unique_id = uuid.uuid4().hex[:8]
    safe_base = secure_filename(base_name)
    filename = f"{safe_base}_{unique_id}{ext}"
    
    # Create key
    # Ensure folder doesn't start with /
    folder = folder.strip("/")
    key = f"{folder}/{filename}"
    
    # Upload to storage
    # We pass BytesIO(file_bytes) to ensure clean read
    storage = get_storage()
    storage.put_file(
        io.BytesIO(file_bytes),
        key,
        content_type=file_storage.content_type or 'application/octet-stream'
    )
    
    return key
