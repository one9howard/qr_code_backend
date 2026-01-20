from utils.storage import get_storage

def get_storage_url(key):
    """
    Template helper to get URL for a storage key.
    Handles both S3 presigned URLs and Local storage paths.
    """
    if not key:
        return ""
    storage = get_storage()
    # Ensure key is treated as relative if needed, but storage handles it.
    # Just pass the key.
    return storage.get_url(key)
