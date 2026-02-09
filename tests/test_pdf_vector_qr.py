"""
Test that PDF QR codes are rendered as vector paths, not raster images.

This test ensures print-grade QR quality by verifying that PDFs generated
with qr_value (and no agent photo) contain ZERO embedded raster images.
"""
import os
import tempfile
import pytest


def test_pdf_vector_qr_no_embedded_images():
    """
    PDFs with qr_value and no agent photo should have 0 embedded images.
    
    This proves the QR is rendered as vector paths, not a raster image.
    """
    # Import PDF generator
    from utils.pdf_generator import generate_pdf_sign
    
    # Create a temp directory for output
    with tempfile.TemporaryDirectory() as tmpdir:
        # Generate PDF with qr_value but NO agent photo
        pdf_path = generate_pdf_sign(
            address="123 Test Street",
            beds="3",
            baths="2",
            sqft="1500",
            price="$450,000",
            agent_name="Test Agent",
            brokerage="Test Brokerage",
            agent_email="test@example.com",
            agent_phone="555-1234",
            qr_path=None,  # No raster QR path
            agent_photo_path=None,  # No agent photo (critical for this test)
            sign_color="#1F6FEB",
            sign_size="18x24",
            order_id=None,  # Will use temp path
            qr_value="https://example.com/r/test123",  # Vector QR URL
        )
        
        # Verify PDF was created
        assert pdf_path is not None
        assert os.path.exists(pdf_path)
        assert os.path.getsize(pdf_path) > 0
        
        # Use PyMuPDF to check for embedded images
        import fitz  # PyMuPDF
        
        doc = fitz.open(pdf_path)
        
        for page_num, page in enumerate(doc):
            images = page.get_images(full=True)
            assert len(images) == 0, (
                f"Page {page_num + 1} has {len(images)} embedded images. "
                "QR should be vector, not raster."
            )
        
        doc.close()


def test_pdf_vector_qr_all_sizes():
    """Test vector QR rendering works for all supported sign sizes."""
    from utils.pdf_generator import generate_pdf_sign
    from constants import SIGN_SIZES
    
    with tempfile.TemporaryDirectory() as tmpdir:
        for sign_size in SIGN_SIZES.keys():
            pdf_path = generate_pdf_sign(
                address="456 Test Ave",
                beds="4",
                baths="3",
                sqft="2000",
                price="$750,000",
                agent_name="Size Test Agent",
                brokerage="Size Test Brokerage",
                agent_email="size@example.com",
                agent_phone="555-5678",
                qr_path=None,
                agent_photo_path=None,
                sign_color="#D45D12",
                sign_size=sign_size,
                order_id=None,
                qr_value="https://example.com/r/sizetest",
            )
            
            assert pdf_path is not None, f"PDF generation failed for size {sign_size}"
            assert os.path.exists(pdf_path), f"PDF not found for size {sign_size}"
            assert os.path.getsize(pdf_path) > 0, f"PDF empty for size {sign_size}"


def test_pdf_with_agent_photo_has_one_image():
    """
    PDFs with agent photo should have exactly 1 embedded image (the photo).
    
    This confirms the QR is still vector even when photos are included.
    """
    from utils.pdf_generator import generate_pdf_sign
    import tempfile
    from PIL import Image
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a dummy agent photo
        photo_path = os.path.join(tmpdir, "agent.jpg")
        img = Image.new('RGB', (200, 200), color='blue')
        img.save(photo_path, 'JPEG')
        
        pdf_path = generate_pdf_sign(
            address="789 Photo Test Blvd",
            beds="5",
            baths="4",
            sqft="3000",
            price="$1,200,000",
            agent_name="Photo Test Agent",
            brokerage="Photo Test Brokerage",
            agent_email="photo@example.com",
            agent_phone="555-9999",
            qr_path=None,
            agent_photo_path=photo_path,  # Include agent photo
            sign_color="#1F6FEB",
            sign_size="18x24",
            order_id=None,
            qr_value="https://example.com/r/phototest",
        )
        
        assert pdf_path is not None
        assert os.path.exists(pdf_path)
        
        import fitz
        doc = fitz.open(pdf_path)
        
        total_images = 0
        for page in doc:
            total_images += len(page.get_images(full=True))
        
        doc.close()
        
        # Should have exactly 1 image (the agent photo)
        # QR should NOT add any images
        assert total_images == 1, (
            f"Expected 1 image (agent photo), got {total_images}. "
            "QR should be vector, not adding to image count."
        )
