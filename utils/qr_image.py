
import logging
import io
import qrcode
from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)

# Try to import pyzbar (requires zbar shared library)
try:
    from pyzbar.pyzbar import decode, ZBarSymbol
    PYZBAR_AVAILABLE = True
except (ImportError, OSError):
    PYZBAR_AVAILABLE = False
    decode = None
    ZBarSymbol = None
    # Log warning only once? Or relies on usage to log.

def render_qr_png(data: str, *, size_px: int = 1024, logo_png: bytes | None = None) -> bytes:
    """
    Render a high-res raster QR code, optionally with a logo overlay.
    """
    
    # 1. Base Setup
    # Use ECC H if logo, else M
    ecc = qrcode.constants.ERROR_CORRECT_H if logo_png else qrcode.constants.ERROR_CORRECT_M
    
    # Create QR object
    qr = qrcode.QRCode(
        version=None, # Auto
        error_correction=ecc,
        box_size=10, # arbitrary base, will resize
        border=4, # Quiet zone (standard is 4 modules)
    )
    qr.add_data(data)
    qr.make(fit=True)
    
    # Render Base QR to PIL Image
    # fill_color="black", back_color="white"
    qr_img = qr.make_image(fill_color="black", back_color="white").convert('RGB')
    
    # Resize to target size_px (High Quality)
    qr_img = qr_img.resize((size_px, size_px), resample=Image.Resampling.LANCZOS)
    
    # If no logo, we are done
    if not logo_png:
        out = io.BytesIO()
        qr_img.save(out, format='PNG')
        return out.getvalue()

    # Safety: If pyzbar not available, we cannot verify logo safety.
    # Fallback to no-logo to be safe (or proceed without verification? 
    # Requirement: "Scan reliability > aesthetics". Verify decode.
    # So if we can't verify, we should NOT use logo.)
    if not PYZBAR_AVAILABLE:
        logger.warning("pyzbar not available (missing DLL?). Falling back to standard QR.")
        out = io.BytesIO()
        qr_img.save(out, format='PNG')
        return out.getvalue()
        
    # 2. Logo Overlay Logic
    try:
        logo = Image.open(io.BytesIO(logo_png)).convert("RGBA")
        
        # Strategies: Ratio of QR width
        # Start at 14% (0.14), drop down if fail
        ratios = [0.14, 0.12, 0.10, 0.08]
        
        for ratio in ratios:
            # Create a working copy of the base QR
            canvas = qr_img.copy()
            width, height = canvas.size
            
            # Calculate Logo Size
            logo_w = int(width * ratio)
            
            # constrain aspects: logo is square-ish normalized
            # Resize logo
            # Keep aspect ratio of logo (it's 512x512 normalized usually, but be safe)
            logo_aspect = logo.width / logo.height
            logo_h = int(logo_w / logo_aspect)
            
            logo_resized = logo.resize((logo_w, logo_h), resample=Image.Resampling.LANCZOS)
            
            # Create White Backing (rounded rectangle preferred, or just rect)
            # Size = logo * 1.15
            back_w = int(logo_w * 1.15)
            back_h = int(logo_h * 1.15)
            
            # Start drawing backing on canvas
            # Center coordinates
            center_x = width // 2
            center_y = height // 2
            
            # Backing coords (top-left)
            back_x = center_x - (back_w // 2)
            back_y = center_y - (back_h // 2)
            
            draw = ImageDraw.Draw(canvas)
            # Draw white rounded rect
            # Radius = 10% of backing width
            radius = back_w // 10
            draw.rounded_rectangle(
                [(back_x, back_y), (back_x + back_w, back_y + back_h)],
                radius=radius,
                fill="white"
            )
            
            # Paste Logo
            logo_x = center_x - (logo_w // 2)
            logo_y = center_y - (logo_h // 2)
            
            # Paste with alpha
            canvas.paste(logo_resized, (logo_x, logo_y), mask=logo_resized)
            
            # 3. VERIFICATION
            # Attempt decode
            decoded_objects = decode(canvas, symbols=[ZBarSymbol.QRCODE])
            
            success = False
            for obj in decoded_objects:
                if obj.data.decode('utf-8') == data:
                    success = True
                    break
            
            if success:
                # Good! Return this image
                out = io.BytesIO()
                canvas.save(out, format='PNG')
                return out.getvalue()
            else:
                logger.warning(f"QR Decode verification failed at ratio {ratio}. Retrying smaller...")
                continue
                
        # If loop finishes without return, fallback
        logger.warning("QR Decode failed at all logo sizes. Falling back to no-logo.")
        out = io.BytesIO()
        # Re-render or just use the base qr_img (which was ECC H)?
        # If we fallback, we might prefer ECC M for cleaner look if we regenerate?
        # But for simplicity, returning the base ECC H (no logo) is safe.
        qr_img.save(out, format='PNG')
        return out.getvalue()
        
    except Exception as e:
        logger.error(f"Logo overlay failed: {e}. Falling back to standard QR.")
        # Fallback to no-logo
        out = io.BytesIO()
        # Create fresh no-logo QR to be safe
        qr_safe = qrcode.make(data, border=4, box_size=10, error_correction=qrcode.constants.ERROR_CORRECT_M)
        qr_safe = qr_safe.resize((size_px, size_px))
        qr_safe.save(out, format='PNG')
        return out.getvalue()
