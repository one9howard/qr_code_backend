"""
Filename utilities for safe, deterministic asset path generation.

Provides sanitization and path generation for PDF signs and preview images.
All generated paths are deterministic based on order_id and layout_version.
"""
import os
import re
from typing import Optional

from config import STATIC_DIR
from constants import LAYOUT_VERSION


def slugify_text(text: str, max_length: int = 60) -> str:
    """
    Convert text to a safe slug: [a-z0-9_-] only, max length enforced.
    
    Args:
        text: Input text to slugify
        max_length: Maximum length of output (default 60)
        
    Returns:
        Safe slug string
    """
    if not text:
        return "unnamed"
    
    # Convert to lowercase
    s = str(text).lower()
    
    # Replace common separators with underscore
    s = re.sub(r'[\s\-./\\,]+', '_', s)
    
    # Remove any character not in allowlist
    s = re.sub(r'[^a-z0-9_-]', '', s)
    
    # Collapse multiple underscores
    s = re.sub(r'_+', '_', s)
    
    # Strip leading/trailing underscores
    s = s.strip('_-')
    
    # Truncate to max length
    if len(s) > max_length:
        s = s[:max_length].rstrip('_-')
    
    return s if s else "unnamed"


def make_sign_asset_basename(
    order_id: int,
    size: str,
    layout_version: Optional[int] = None
) -> str:
    """
    Generate a deterministic, safe basename for sign assets.
    
    Args:
        order_id: The order ID
        size: Sign size (e.g., "18x24", "36x18")
        layout_version: Layout version number (defaults to LAYOUT_VERSION constant)
        
    Returns:
        Safe basename like "sign_18x24_v1"
    """
    if layout_version is None:
        layout_version = LAYOUT_VERSION
    
    # Sanitize size (should already be canonical, but be safe)
    safe_size = re.sub(r'[^0-9x]', '', size.lower())
    if not safe_size:
        safe_size = "18x24"
    
    return f"sign_{safe_size}_v{layout_version}"


def get_order_asset_dir(order_id: int, create: bool = True) -> str:
    """
    Get the asset directory for an order.
    
    Args:
        order_id: The order ID
        create: Whether to create the directory if it doesn't exist
        
    Returns:
        Absolute path to static/generated/order_<id>/
    """
    asset_dir = os.path.join(STATIC_DIR, "generated", f"order_{order_id}")
    
    if create:
        os.makedirs(asset_dir, exist_ok=True)
    
    return asset_dir


def get_pdf_path(order_id: int, size: str, layout_version: Optional[int] = None) -> str:
    """
    Get the full path for a sign PDF.
    
    Args:
        order_id: The order ID
        size: Sign size (e.g., "18x24")
        layout_version: Layout version (defaults to LAYOUT_VERSION)
        
    Returns:
        Absolute path to the PDF file
    """
    asset_dir = get_order_asset_dir(order_id)
    basename = make_sign_asset_basename(order_id, size, layout_version)
    return os.path.join(asset_dir, f"{basename}.pdf")


def get_preview_path(order_id: int, size: str, layout_version: Optional[int] = None) -> str:
    """
    Get the full path for a sign preview image.
    
    Args:
        order_id: The order ID
        size: Sign size (e.g., "18x24")
        layout_version: Layout version (defaults to LAYOUT_VERSION)
        
    Returns:
        Absolute path to the preview file (WebP)
    """
    asset_dir = get_order_asset_dir(order_id)
    basename = make_sign_asset_basename(order_id, size, layout_version)
    return os.path.join(asset_dir, f"{basename}_preview.webp")


def get_relative_asset_path(absolute_path: str) -> str:
    """
    Convert absolute asset path to relative path from static folder.
    
    Args:
        absolute_path: Full filesystem path
        
    Returns:
        Path relative to static/ for use in URLs
    """
    if STATIC_DIR in absolute_path:
        return absolute_path.replace(STATIC_DIR + os.sep, "").replace("\\", "/")
    return absolute_path


def get_legacy_pdf_path(pdf_filename: str) -> Optional[str]:
    """
    Resolve legacy PDF path (pre-order-directory structure).
    
    Args:
        pdf_filename: The filename stored in DB (may be basename or full path)
        
    Returns:
        Full path if file exists, None otherwise
    """
    from config import PDF_PATH
    
    # If it's a basename, check legacy location
    if not os.path.isabs(pdf_filename):
        legacy_path = os.path.join(PDF_PATH, pdf_filename)
        if os.path.exists(legacy_path):
            return legacy_path
    
    # If it's an absolute path, check if it exists
    if os.path.exists(pdf_filename):
        return pdf_filename
    
    return None


# ============================================================================
# Private PDF Path Functions (for secure, non-public PDF storage)
# ============================================================================

def get_private_pdf_dir(order_id: int, create: bool = True) -> str:
    """
    Get the private PDF directory for an order.
    
    Args:
        order_id: The order ID
        create: Whether to create the directory if it doesn't exist
        
    Returns:
        Absolute path to private/pdf/order_<id>/
    """
    from config import PRIVATE_PDF_DIR
    
    pdf_dir = os.path.join(PRIVATE_PDF_DIR, f"order_{order_id}")
    
    if create:
        os.makedirs(pdf_dir, exist_ok=True)
    
    return pdf_dir


def get_private_pdf_path(order_id: int, size: str, layout_version: Optional[int] = None) -> str:
    """
    Get the full path for a private PDF.
    
    Args:
        order_id: The order ID
        size: Sign size (e.g., "18x24")
        layout_version: Layout version (defaults to LAYOUT_VERSION)
        
    Returns:
        Absolute path to the private PDF file
    """
    pdf_dir = get_private_pdf_dir(order_id)
    basename = make_sign_asset_basename(order_id, size, layout_version)
    return os.path.join(pdf_dir, f"{basename}.pdf")


def get_private_pdf_relative_path(order_id: int, size: str, layout_version: Optional[int] = None) -> str:
    """
    Get the relative path for storing in DB (relative to PRIVATE_PDF_DIR).
    
    Args:
        order_id: The order ID
        size: Sign size (e.g., "18x24")
        layout_version: Layout version (defaults to LAYOUT_VERSION)
        
    Returns:
        Relative path like "order_123/sign_18x24_v1.pdf"
    """
    basename = make_sign_asset_basename(order_id, size, layout_version)
    return f"order_{order_id}/{basename}.pdf"


# ============================================================================
# Private Preview Path Functions (for secure, non-public preview storage)
# ============================================================================

def get_order_private_preview_dir(order_id: int, create: bool = True) -> str:
    """
    Get the private preview directory for an order.
    
    Args:
        order_id: The order ID
        create: Whether to create the directory if it doesn't exist
        
    Returns:
        Absolute path to private/previews/order_<id>/
    """
    from config import PRIVATE_PREVIEW_DIR
    
    preview_dir = os.path.join(PRIVATE_PREVIEW_DIR, f"order_{order_id}")
    
    if create:
        os.makedirs(preview_dir, exist_ok=True)
    
    return preview_dir


def get_private_preview_path(order_id: int, size: str, layout_version: Optional[int] = None) -> str:
    """
    Get the full path for a private preview image.
    
    Args:
        order_id: The order ID
        size: Sign size (e.g., "18x24")
        layout_version: Layout version (defaults to LAYOUT_VERSION)
        
    Returns:
        Absolute path to the private preview file (WebP)
    """
    preview_dir = get_order_private_preview_dir(order_id)
    basename = make_sign_asset_basename(order_id, size, layout_version)
    return os.path.join(preview_dir, f"{basename}_preview.webp")


def get_temp_pdf_path(size: str, layout_version: Optional[int] = None) -> str:
    """
    Get a temporary PDF path for when order_id is not yet known.
    
    Args:
        size: Sign size (e.g., "18x24")
        layout_version: Layout version (defaults to LAYOUT_VERSION)
        
    Returns:
        Absolute path to a temp PDF file
    """
    import uuid
    from config import PRIVATE_PDF_DIR
    
    temp_dir = os.path.join(PRIVATE_PDF_DIR, "tmp")
    os.makedirs(temp_dir, exist_ok=True)
    
    if layout_version is None:
        layout_version = LAYOUT_VERSION
    
    # Use UUID to avoid collisions
    unique_id = uuid.uuid4().hex[:8]
    safe_size = re.sub(r'[^0-9x]', '', size.lower()) or "18x24"
    
    return os.path.join(temp_dir, f"temp_{unique_id}_{safe_size}_v{layout_version}.pdf")


def resolve_pdf_path(pdf_path_from_db: str) -> Optional[str]:
    """
    Resolve a DB-stored PDF path to an absolute filesystem path.
    
    SECURITY: Blocks path traversal attacks (.., absolute paths).
    Only allows:
    - Private paths: order_<id>/... under PRIVATE_PDF_DIR
    - Legacy basenames: <filename>.pdf under static/pdf/
    
    Args:
        pdf_path_from_db: The path stored in orders.sign_pdf_path
        
    Returns:
        Absolute filesystem path if valid and exists, None otherwise
    """
    from config import PRIVATE_PDF_DIR, PDF_PATH
    
    if not pdf_path_from_db:
        return None
    
    # Normalize path separators
    normalized = pdf_path_from_db.replace("\\", "/")
    
    # SECURITY: Block absolute paths
    if os.path.isabs(pdf_path_from_db):
        print(f"[Security] Blocked absolute path: {pdf_path_from_db}")
        return None
    
    # SECURITY: Block path traversal
    if ".." in normalized:
        print(f"[Security] Blocked path traversal: {pdf_path_from_db}")
        return None
    
    # SECURITY: Block paths starting with / or containing drive letters
    if normalized.startswith("/") or (len(normalized) > 1 and normalized[1] == ":"):
        print(f"[Security] Blocked suspicious path: {pdf_path_from_db}")
        return None
    
    # Check if it's a new private path (order_<id>/...)
    if normalized.startswith("order_"):
        # Validate format: order_<digits>/<filename>
        parts = normalized.split("/")
        if len(parts) >= 2 and parts[0].startswith("order_"):
            try:
                # Verify the order ID part is numeric
                order_id_str = parts[0].replace("order_", "")
                int(order_id_str)  # Will raise if not numeric
                
                # Construct full path
                full_path = os.path.join(PRIVATE_PDF_DIR, normalized)
                
                # Verify the resolved path is still under PRIVATE_PDF_DIR (defense in depth)
                real_path = os.path.realpath(full_path)
                real_private = os.path.realpath(PRIVATE_PDF_DIR)
                
                if not real_path.startswith(real_private):
                    print(f"[Security] Path escaped private dir: {pdf_path_from_db}")
                    return None
                
                if os.path.exists(full_path):
                    return full_path
            except ValueError:
                pass  # Not a valid order ID format
    
    # Legacy fallback: treat as basename in static/pdf/
    # Only allow simple filenames (no slashes after normalization check)
    if "/" not in normalized and "\\" not in pdf_path_from_db:
        legacy_path = os.path.join(PDF_PATH, pdf_path_from_db)
        
        # Verify resolved path is under PDF_PATH
        real_path = os.path.realpath(legacy_path)
        real_pdf_path = os.path.realpath(PDF_PATH)
        
        if real_path.startswith(real_pdf_path) and os.path.exists(legacy_path):
            return legacy_path
    
    return None

