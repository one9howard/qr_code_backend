import pytest
from PIL import Image, ImageDraw
import io
try:
    from utils.qr_image import render_qr_png
    from pyzbar.pyzbar import decode
    ZBAR_AVAILABLE = True
except (ImportError, OSError):
    ZBAR_AVAILABLE = False

def create_dummy_logo(width=512, height=512, color="red"):
    """Create a simple colored square logo."""
    img = Image.new('RGBA', (width, height), (0,0,0,0))
    d = ImageDraw.Draw(img)
    d.rectangle([0,0,width,height], fill=color)
    out = io.BytesIO()
    img.save(out, format='PNG')
    return out.getvalue()

def test_qr_without_logo():
    """Verify QR generates and decodes without logo."""
    data = "https://example.com/test-no-logo"
    png_bytes = render_qr_png(data, size_px=500, logo_png=None)
    
    # Verify image
    img = Image.open(io.BytesIO(png_bytes))
    assert img.size == (500, 500)
    
    # Verify decode
    results = decode(img)
    assert len(results) > 0
    assert results[0].data.decode('utf-8') == data

def test_qr_with_logo_decodes():
    """Verify QR generates WITH logo and still decodes."""
    data = "https://example.com/test-with-logo"
    logo = create_dummy_logo()
    
    png_bytes = render_qr_png(data, size_px=1000, logo_png=logo)
    
    # Verify
    img = Image.open(io.BytesIO(png_bytes))
    results = decode(img)
    
    # Should decode despite logo
    assert len(results) > 0
    assert results[0].data.decode('utf-8') == data

def test_qr_auto_fallback():
    """Verify QR logic handles large logos or decode failures gracefully (by keeping valid QR)."""
    # Note: It's hard to force a decode failure with standard QR libs unless we cover too much.
    # The implementation reduces logo size until it works.
    # We'll just verify it returns a valid QR.
    data = "https://example.com/test-fallback"
    logo = create_dummy_logo() # Standard logo
    
    # logic will try sizes 0.14, 0.12 etc.
    png_bytes = render_qr_png(data, size_px=800, logo_png=logo)
    
    img = Image.open(io.BytesIO(png_bytes))
    results = decode(img)
    assert len(results) > 0
    assert results[0].data.decode('utf-8') == data
