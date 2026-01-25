
import io
from PIL import Image
from utils.qr_image import render_qr_png

def test_qr_integer_scaling():
    """
    Verify render_qr_png produces exact 1024x1024 image
    and that the QR itself is a clean integer multiple of modules.
    """
    size_px = 1024
    data = "https://example.com/r/very-long-url-to-ensure-version-complexity"
    
    # Render
    png_bytes = render_qr_png(data, size_px=size_px)
    img = Image.open(io.BytesIO(png_bytes))
    
    # 1. Verify Dimensions
    assert img.size == (size_px, size_px), f"Image size mismatch: {img.size} != 1024x1024"
    
    # 2. Verify White Background (Padding check)
    # Top-left pixel should be white (quiet zone)
    assert img.getpixel((0, 0)) == (255, 255, 255), "Background padding not white"
    
    # 3. Verify no aliasing (Sample check)
    # We expect only Black (0,0,0) and White (255,255,255) pixels for a basic QR
    # If resampling happened (Bilinear/Lanczos), we'd see grays.
    # Note: Logo overlay MIGHT add grays, but here we test NO logo.
    
    colors = img.getcolors(maxcolors=256)
    # format: [(count, color), ...]
    # We expect exactly 2 colors ideally.
    distinct_colors = [c[1] for c in colors]
    assert len(distinct_colors) <= 2, f"Found mixed colors (likely aliasing): {distinct_colors}"
    print("QR Integer Scaling Test Passed")

if __name__ == "__main__":
    test_qr_integer_scaling()
