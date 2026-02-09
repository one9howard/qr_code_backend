"""
LocalStorage Security Tests

Tests for path traversal protection in LocalStorage.
"""
import pytest
import os
import tempfile


class TestLocalStorageSecurity:
    
    def test_path_traversal_with_dotdot_raises_error(self, app):
        """Path traversal with ../ should raise ValueError."""
        with app.app_context():
            from utils.storage import LocalStorage
            
            with tempfile.TemporaryDirectory() as tmpdir:
                storage = LocalStorage(tmpdir, "http://localhost")
                
                # Attempt path traversal
                with pytest.raises(ValueError, match="traversal"):
                    storage._get_abs_path("../secrets.txt")
                
                with pytest.raises(ValueError, match="traversal"):
                    storage._get_abs_path("foo/../../etc/passwd")
                
                with pytest.raises(ValueError, match="traversal"):
                    storage._get_abs_path("uploads/../../../sensitive.txt")
    
    def test_path_traversal_with_absolute_path_raises_error(self, app):
        """Absolute paths outside base_dir should raise ValueError."""
        with app.app_context():
            from utils.storage import LocalStorage
            
            with tempfile.TemporaryDirectory() as tmpdir:
                storage = LocalStorage(tmpdir, "http://localhost")
                
                # On Windows, this might look different
                if os.name == 'nt':
                    with pytest.raises(ValueError, match="traversal"):
                        storage._get_abs_path("C:\\Windows\\System32\\config")
                else:
                    with pytest.raises(ValueError, match="traversal"):
                        storage._get_abs_path("/etc/passwd")
    
    def test_normal_paths_work_correctly(self, app):
        """Normal relative paths should work without error."""
        with app.app_context():
            from utils.storage import LocalStorage
            
            with tempfile.TemporaryDirectory() as tmpdir:
                storage = LocalStorage(tmpdir, "http://localhost")
                
                # These should NOT raise
                path1 = storage._get_abs_path("uploads/test.jpg")
                assert path1.startswith(tmpdir)
                
                path2 = storage._get_abs_path("pdfs/order_123/sign.pdf")
                assert path2.startswith(tmpdir)
                
                path3 = storage._get_abs_path("simple.txt")
                assert path3.startswith(tmpdir)
    
    def test_get_url_returns_storage_path(self, app):
        """get_url should return /storage/ prefixed path."""
        with app.app_context():
            from utils.storage import LocalStorage
            
            with tempfile.TemporaryDirectory() as tmpdir:
                storage = LocalStorage(tmpdir, "http://localhost:5000")
                
                url = storage.get_url("uploads/test.jpg")
                assert "/storage/" in url
                assert url == "http://localhost:5000/storage/uploads/test.jpg"
    
    def test_put_and_get_with_safe_path(self, app):
        """Normal put/get operations should work."""
        with app.app_context():
            from utils.storage import LocalStorage
            import io
            
            with tempfile.TemporaryDirectory() as tmpdir:
                storage = LocalStorage(tmpdir, "http://localhost")
                
                # Put a file
                content = b"test content"
                buf = io.BytesIO(content)
                key = "test/file.txt"
                storage.put_file(buf, key)
                
                # Get it back
                result = storage.get_file(key)
                assert result.read() == content
                
                # Exists should work
                assert storage.exists(key) is True
                assert storage.exists("nonexistent.txt") is False
    
    def test_get_file_with_traversal_raises(self, app):
        """get_file with traversal path should raise."""
        with app.app_context():
            from utils.storage import LocalStorage
            
            with tempfile.TemporaryDirectory() as tmpdir:
                storage = LocalStorage(tmpdir, "http://localhost")
                
                with pytest.raises(ValueError, match="traversal"):
                    storage.get_file("../../../etc/passwd")
