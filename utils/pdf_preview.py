"""
PDF Preview Generator - Web Optimized.

Renders PDF first page to WebP preview with aspect ratio preservation.
Supports per-order directory structure and atomic generation via storage abstraction.
"""
import os
import io
from typing import Optional, Tuple

import fitz  # PyMuPDF
from PIL import Image

from constants import SIGN_SIZES, DEFAULT_SIGN_SIZE, LAYOUT_VERSION
from utils.storage import get_storage
from utils.filenames import make_sign_asset_basename

# Web preview settings
MAX_PREVIEW_DIMENSION = 1800  # Max width or height in pixels
PREVIEW_QUALITY = 85  # WebP quality (0-100)
RENDER_DPI = 150  # DPI for initial PDF render


def _calculate_scaled_dimensions(
    width: int, height: int, max_dimension: int
) -> Tuple[int, int]:
    """
    Calculate new dimensions preserving aspect ratio, capped at max_dimension.
    """
    if width <= max_dimension and height <= max_dimension:
        return width, height
    
    # Calculate scale factor based on which dimension is larger
    if width > height:
        scale = max_dimension / width
    else:
        scale = max_dimension / height
    
    new_width = int(width * scale)
    new_height = int(height * scale)
    
    return new_width, new_height


def render_pdf_to_web_preview(
    pdf_key: str,
    order_id: Optional[int] = None,
    sign_size: Optional[str] = None,
    max_dimension: int = MAX_PREVIEW_DIMENSION,
    layout_version: Optional[int] = None,
    bleed_in: float = 0.125,
) -> str:
    """
    Render PDF to web-optimized WebP preview with aspect ratio preservation.
    Reads PDF from storage and saves preview to storage.
    
    Args:
        pdf_key: Storage key for the PDF file
        order_id: Order ID for per-order directory structure
        sign_size: Sign size string (e.g., "18x24", "36x18")
        max_dimension: Maximum width or height for the preview
        layout_version: Layout version for filename (defaults to LAYOUT_VERSION)
        bleed_in: Bleed in inches to crop from edges
        
    Returns:
        str: Storage key of the generated preview file
    """
    if not sign_size:
        sign_size = DEFAULT_SIGN_SIZE
    
    if layout_version is None:
        layout_version = LAYOUT_VERSION
    
    storage = get_storage()
    
    # Fetch PDF bytes
    try:
        pdf_file = storage.get_file(pdf_key)
        # Normalize to bytes (Fix P0)
        if hasattr(pdf_file, 'read'):
            pdf_bytes = pdf_file.read()
            if hasattr(pdf_file, 'seek'):
                pdf_file.seek(0) # Reset just in case shared
        elif isinstance(pdf_file, bytes):
            pdf_bytes = pdf_file
        elif hasattr(pdf_file, 'getvalue'):
            pdf_bytes = pdf_file.getvalue()
        else:
            # Fallback or error
            raise ValueError(f"Unknown storage return type: {type(pdf_file)}")
            
    except Exception as e:
        raise RuntimeError(f"Failed to fetch PDF from storage key {pdf_key}: {e}")
    
    # Open PDF from memory
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    
    try:
        page = doc.load_page(0)
        
        # Render at fixed DPI
        zoom = RENDER_DPI / 72.0
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        
        # Crop bleed
        bleed_px = int(round(bleed_in * RENDER_DPI))
        if bleed_px > 0 and img.width > 2 * bleed_px and img.height > 2 * bleed_px:
            img = img.crop((bleed_px, bleed_px, img.width - bleed_px, img.height - bleed_px))
        
        # Scale to max dimension while preserving aspect ratio
        new_width, new_height = _calculate_scaled_dimensions(
            img.width, img.height, max_dimension
        )
        
        if (new_width, new_height) != img.size:
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        # Save as WebP to buffer
        img_buffer = io.BytesIO()
        img.save(img_buffer, format="WEBP", quality=PREVIEW_QUALITY)
        img_buffer.seek(0)
        
        # Determine output key
        if order_id:
            folder = f"previews/order_{order_id}"
        else:
            folder = "previews/tmp"
            
        basename = make_sign_asset_basename(order_id if order_id else 0, sign_size, layout_version)
        preview_key = f"{folder}/{basename}.webp"
        
        # Upload to storage
        storage.put_file(img_buffer, preview_key, content_type="image/webp")
        
        return preview_key
        
    finally:
        doc.close()


def regenerate_order_preview(
    order_id: int,
    pdf_key: str,
    sign_size: str,
) -> str:
    """
    Regenerate preview for an existing order.
    """
    return render_pdf_to_web_preview(
        pdf_key=pdf_key,
        order_id=order_id,
        sign_size=sign_size,
    )
