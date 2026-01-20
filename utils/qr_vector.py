"""
Vector QR Code Drawing for ReportLab PDFs.

Uses ReportLab's QrCodeWidget for true vector QR rendering.
No raster scaling - QR is rendered as vector paths.
"""
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.graphics import renderPDF
from reportlab.lib import colors


def draw_vector_qr(c, qr_value: str, x: float, y: float, size: float, 
                   quiet: float = 0, ecc_level: str = "H") -> None:
    """
    Draw a QR code as vector paths on a ReportLab canvas using QrCodeWidget.
    
    Args:
        c: ReportLab canvas object
        qr_value: Data to encode (typically a URL)
        x: X position (bottom-left of QR, not quiet zone) in points
        y: Y position (bottom-left of QR, not quiet zone) in points
        size: QR code size in points (not including quiet zone)
        quiet: Quiet zone size in points (drawn as white around QR)
        ecc_level: Error correction level ('L', 'M', 'Q', 'H')
    
    Notes:
        - Uses ReportLab's QrCodeWidget for true vector output
        - Quiet zone is drawn as white background first
        - QR modules are black on white
    """
    if not qr_value:
        return
    
    # Draw white background for quiet zone
    if quiet > 0:
        c.setFillColorRGB(1, 1, 1)
        c.rect(x - quiet, y - quiet, size + 2 * quiet, size + 2 * quiet, 
               stroke=0, fill=1)
    
    # Create QR widget with specified error correction
    qr = QrCodeWidget(qr_value, barLevel=ecc_level)
    
    # Get widget bounds to calculate scale
    bounds = qr.getBounds()
    qr_width = bounds[2] - bounds[0]
    qr_height = bounds[3] - bounds[1]
    
    if qr_width <= 0 or qr_height <= 0:
        return
    
    # Create a Drawing with transform to scale to target size
    scale_x = size / qr_width
    scale_y = size / qr_height
    
    d = Drawing(size, size)
    d.add(qr)
    d.transform = [scale_x, 0, 0, scale_y, -bounds[0] * scale_x, -bounds[1] * scale_y]
    
    # Render the Drawing onto the canvas
    renderPDF.draw(d, c, x, y)


# Legacy alias for compatibility
def draw_qr_vector(canvas, x: float, y: float, size: float, qr_data: str,
                   error_correction=None, module_color: tuple = (0, 0, 0),
                   bg_color: tuple = (1, 1, 1)) -> None:
    """
    Legacy wrapper - calls draw_vector_qr with quiet zone.
    
    Kept for backwards compatibility with existing call sites.
    """
    # Calculate a reasonable quiet zone (4 modules worth, ~10% of size)
    quiet = size * 0.1
    draw_vector_qr(canvas, qr_data, x, y, size, quiet=quiet, ecc_level="H")
