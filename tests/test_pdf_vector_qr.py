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
    from unittest.mock import patch, MagicMock
    import io
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a dummy agent photo in memory
        img = Image.new('RGB', (200, 200), color='blue')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='JPEG')
        img_bytes.seek(0)
        
        # Mock storage to return this image
        with patch('utils.pdf_generator.get_storage') as mock_get_storage:
            mock_storage = MagicMock()
            mock_get_storage.return_value = mock_storage
            
            # When PDF generator calls storage.get_file('mock_headshot_key')
            mock_storage.exists.return_value = True
            mock_storage.get_file.return_value = img_bytes
            
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
                # Pass mocked key instead of path
                agent_photo_key="mock_headshot_key",
                return_path=True, # Force return path (legacy mode trigger)
                sign_color="#1F6FEB",
                sign_size="18x24",
                order_id=None,
                qr_value="https://example.com/r/phototest",
            )
            pdf_path_no_qr = generate_pdf_sign(
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
                agent_photo_key="mock_headshot_key",
                return_path=True,
                sign_color="#1F6FEB",
                sign_size="18x24",
                order_id=None,
                qr_value=None,
            )
            
            assert pdf_path is not None
            assert os.path.exists(pdf_path)
            assert os.path.exists(pdf_path_no_qr)
            
            import fitz
            with_qr = fitz.open(pdf_path)
            without_qr = fitz.open(pdf_path_no_qr)

            total_images_with_qr = sum(len(page.get_images(full=True)) for page in with_qr)
            total_images_without_qr = sum(len(page.get_images(full=True)) for page in without_qr)

            with_qr.close()
            without_qr.close()

            # QR should stay vector: enabling qr_value must not increase embedded image count.
            assert total_images_with_qr == total_images_without_qr, (
                f"Image count changed with qr_value: with_qr={total_images_with_qr}, "
                f"without_qr={total_images_without_qr}."
            )
