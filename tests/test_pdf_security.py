"""
Unit tests for PDF security features.

Tests:
- resolve_pdf_path() path traversal blocking
- resolve_pdf_path() valid path resolution
"""
import os
import sys
import tempfile
import unittest

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestResolvePdfPath(unittest.TestCase):
    """Tests for utils.filenames.resolve_pdf_path security."""
    
    def test_blocks_absolute_paths(self):
        """Should block absolute paths."""
        from utils.filenames import resolve_pdf_path
        
        # Unix-style absolute path
        result = resolve_pdf_path("/etc/passwd")
        self.assertIsNone(result)
        
        # Windows-style absolute path
        result = resolve_pdf_path("C:\\Windows\\System32\\config")
        self.assertIsNone(result)
    
    def test_blocks_path_traversal(self):
        """Should block path traversal attempts."""
        from utils.filenames import resolve_pdf_path
        
        # Parent directory traversal
        result = resolve_pdf_path("../../../etc/passwd")
        self.assertIsNone(result)
        
        result = resolve_pdf_path("order_1/../../etc/passwd")
        self.assertIsNone(result)
        
        # Mixed slashes
        result = resolve_pdf_path("..\\..\\etc\\passwd")
        self.assertIsNone(result)
    
    def test_blocks_leading_slash(self):
        """Should block paths starting with /."""
        from utils.filenames import resolve_pdf_path
        
        result = resolve_pdf_path("/order_1/sign.pdf")
        self.assertIsNone(result)
    
    def test_allows_valid_order_path_format(self):
        """Should accept valid order path format (file must exist for success)."""
        from utils.filenames import resolve_pdf_path
        from config import PRIVATE_PDF_DIR
        
        # Create a temporary test file
        test_order_dir = os.path.join(PRIVATE_PDF_DIR, "order_999999")
        os.makedirs(test_order_dir, exist_ok=True)
        test_file = os.path.join(test_order_dir, "sign_18x24_v1.pdf")
        
        try:
            # Create test file
            with open(test_file, 'w') as f:
                f.write("test")
            
            # Should resolve successfully
            result = resolve_pdf_path("order_999999/sign_18x24_v1.pdf")
            self.assertIsNotNone(result)
            self.assertTrue(os.path.exists(result))
        finally:
            # Cleanup
            if os.path.exists(test_file):
                os.remove(test_file)
            if os.path.exists(test_order_dir):
                os.rmdir(test_order_dir)
    
    def test_rejects_invalid_order_id_format(self):
        """Should reject order paths with non-numeric IDs."""
        from utils.filenames import resolve_pdf_path
        
        result = resolve_pdf_path("order_abc/sign.pdf")
        self.assertIsNone(result)
        
        result = resolve_pdf_path("order_/sign.pdf")
        self.assertIsNone(result)
    
    def test_empty_and_none_input(self):
        """Should handle empty and None inputs."""
        from utils.filenames import resolve_pdf_path
        
        result = resolve_pdf_path("")
        self.assertIsNone(result)
        
        result = resolve_pdf_path(None)
        self.assertIsNone(result)


class TestPrivatePdfPaths(unittest.TestCase):
    """Tests for private PDF path generation."""
    
    def test_get_private_pdf_path_format(self):
        """Should generate correct path format."""
        from utils.filenames import get_private_pdf_path
        from config import PRIVATE_PDF_DIR
        
        path = get_private_pdf_path(123, "18x24", 1)
        
        self.assertIn("order_123", path)
        self.assertIn("18x24", path)
        self.assertTrue(path.endswith(".pdf"))
        self.assertTrue(path.startswith(PRIVATE_PDF_DIR))
    
    def test_get_private_pdf_relative_path_format(self):
        """Should generate correct relative path format."""
        from utils.filenames import get_private_pdf_relative_path
        
        path = get_private_pdf_relative_path(456, "24x36", 1)
        
        self.assertTrue(path.startswith("order_456/"))
        self.assertIn("24x36", path)
        self.assertTrue(path.endswith(".pdf"))
        # Should not be absolute
        self.assertFalse(os.path.isabs(path))


class TestPaidStatuses(unittest.TestCase):
    """Tests for PAID_STATUSES constant."""
    
    def test_paid_statuses_contains_expected_values(self):
        """PAID_STATUSES should contain expected status values."""
        from constants import (
            PAID_STATUSES,
            ORDER_STATUS_PAID,
            ORDER_STATUS_SUBMITTED_TO_PRINTER,
            ORDER_STATUS_FULFILLED,
            ORDER_STATUS_PENDING_PAYMENT
        )
        
        self.assertIn(ORDER_STATUS_PAID, PAID_STATUSES)
        self.assertIn(ORDER_STATUS_SUBMITTED_TO_PRINTER, PAID_STATUSES)
        self.assertIn(ORDER_STATUS_FULFILLED, PAID_STATUSES)
        
        # Should NOT contain pending_payment
        self.assertNotIn(ORDER_STATUS_PENDING_PAYMENT, PAID_STATUSES)


if __name__ == "__main__":
    unittest.main()
