"""
Storage Files Blueprint - Dev-only file serving for local storage.
Only active when STORAGE_BACKEND == 'local' and APP_STAGE != 'production'.
"""
from flask import Blueprint, abort, send_file
from config import STORAGE_BACKEND, APP_STAGE

storage_files_bp = Blueprint('storage_files', __name__)


@storage_files_bp.route('/storage/<path:key>')
def serve_storage_file(key):
    """
    Serve files from local storage in development/staging.
    Returns 404 for missing files or if disabled.
    """
    # Security: Only serve in local storage mode and non-production
    if STORAGE_BACKEND != 'local' or APP_STAGE == 'production':
        abort(404)
    
    from utils.storage import get_storage
    
    storage = get_storage()
    
    try:
        if not storage.exists(key):
            abort(404)
        
        file_data = storage.get_file(key)
        
        # Determine content type from extension
        import mimetypes
        content_type, _ = mimetypes.guess_type(key)
        if not content_type:
            content_type = 'application/octet-stream'
        
        return send_file(
            file_data,
            mimetype=content_type,
            as_attachment=False
        )
    except ValueError:
        # Path traversal attempt
        abort(404)
    except FileNotFoundError:
        abort(404)
