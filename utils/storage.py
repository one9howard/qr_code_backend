import os
import boto3
from werkzeug.utils import secure_filename
from flask import current_app
from io import BytesIO

class StorageBackend:
    def put_file(self, file_storage, key, content_type=None):
        raise NotImplementedError
    
    def get_url(self, key, expires_seconds=3600):
        raise NotImplementedError

    def get_file(self, key):
        """Returns file content as bytes-like object (BytesIO)."""
        raise NotImplementedError

    def delete(self, key):
        raise NotImplementedError

    def exists(self, key):
        raise NotImplementedError

    def copy(self, src_key, dest_key):
        raise NotImplementedError

class LocalStorage(StorageBackend):
    def __init__(self, base_dir, base_url):
        self.base_dir = base_dir
        self.base_url = base_url
        os.makedirs(self.base_dir, exist_ok=True)

    def _get_abs_path(self, key):
        # Prevent traversal
        filename = secure_filename(os.path.basename(key))
        folder = os.path.dirname(key)
        # Simply join base_dir + key
        # We assume key is relative path like "uploads/properties/123.jpg"
        return os.path.join(self.base_dir, key)

    def put_file(self, file_storage, key, content_type=None):
        abs_path = self._get_abs_path(key)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        
        # If it's a werkzeug FileStorage
        if hasattr(file_storage, 'save'):
            # Reset pointer just in case
            file_storage.seek(0)
            file_storage.save(abs_path)
            file_storage.seek(0) # Reset for subsequent uses
        else:
            # It's bytes or file-like
            mode = 'wb' if isinstance(file_storage, bytes) else 'w'
            if hasattr(file_storage, 'read'):
               file_storage.seek(0)
               data = file_storage.read()
               file_storage.seek(0)
               with open(abs_path, 'wb') as f:
                   f.write(data)
            else:
                 with open(abs_path, mode) as f:
                    f.write(file_storage)
        return key

    def get_url(self, key, expires_seconds=3600):
        # Local URL (served via static or route)
        # We handle this by mapping raw keys to URLs
        return f"{self.base_url}/{key}".replace("\\", "/")

    def get_file(self, key):
        abs_path = self._get_abs_path(key)
        with open(abs_path, 'rb') as f:
            return BytesIO(f.read())

    def delete(self, key):
        abs_path = self._get_abs_path(key)
        if os.path.exists(abs_path):
            os.remove(abs_path)

    def exists(self, key):
        return os.path.exists(self._get_abs_path(key))

    def copy(self, src_key, dest_key):
        src_path = self._get_abs_path(src_key)
        dest_path = self._get_abs_path(dest_key)
        
        if not os.path.exists(src_path):
             raise FileNotFoundError(f"Source file {src_key} not found")
             
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        import shutil
        shutil.copy2(src_path, dest_path)

class S3Storage(StorageBackend):
    def __init__(self, bucket_name, region, access_key, secret_key, prefix=""):
        self.s3 = boto3.client(
            's3',
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key
        )
        self.bucket = bucket_name
        self.prefix = prefix

    def _get_s3_key(self, key):
        # Use provided key directly, assuming caller handles prefix/structure
        # But if valid prefix configured globally, prepend it?
        if self.prefix:
             # Ensure no double slashes
             return f"{self.prefix.rstrip('/')}/{key.lstrip('/')}"
        return key

    def put_file(self, file_storage, key, content_type=None):
        full_key = self._get_s3_key(key)
        
        # Determine content type
        if not content_type:
            content_type = "application/octet-stream"
            if hasattr(file_storage, 'content_type') and file_storage.content_type:
                content_type = file_storage.content_type

        # Get bytes
        body = file_storage
        if hasattr(file_storage, 'read'):
            file_storage.seek(0)
            body = file_storage.read()
            file_storage.seek(0)

        self.s3.put_object(
            Bucket=self.bucket,
            Key=full_key,
            Body=body,
            ContentType=content_type,
            # Private by default (no ACL)
        )
        return key

    def get_url(self, key, expires_seconds=3600):
        full_key = self._get_s3_key(key)
        try:
            url = self.s3.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket, 'Key': full_key},
                ExpiresIn=expires_seconds
            )
            return url
        except Exception as e:
            print(f"Error generating presigned URL: {e}")
            return ""

    def get_file(self, key):
        full_key = self._get_s3_key(key)
        obj = self.s3.get_object(Bucket=self.bucket, Key=full_key)
        return BytesIO(obj['Body'].read())

    def delete(self, key):
        full_key = self._get_s3_key(key)
        self.s3.delete_object(Bucket=self.bucket, Key=full_key)

    def exists(self, key):
        full_key = self._get_s3_key(key)
        try:
            self.s3.head_object(Bucket=self.bucket, Key=full_key)
            return True
        except:
            return False

    def copy(self, src_key, dest_key):
        src_full_key = self._get_s3_key(src_key)
        dest_full_key = self._get_s3_key(dest_key)
        
        copy_source = {
            'Bucket': self.bucket,
            'Key': src_full_key
        }
        self.s3.copy_object(CopySource=copy_source, Bucket=self.bucket, Key=dest_full_key)

def get_storage():
    """Factory to return the configured storage backend."""
    from config import STORAGE_BACKEND, S3_BUCKET, AWS_REGION, INSTANCE_DIR, BASE_URL, S3_PREFIX
    
    if STORAGE_BACKEND == 's3':
        access_key = os.environ.get('AWS_ACCESS_KEY_ID')
        secret_key = os.environ.get('AWS_SECRET_ACCESS_KEY')
        
        if not access_key or not secret_key:
             # If we are in production and missing keys, we should probably warn or fail
             print("[Storage] WARNING: S3 backend selected but AWS credentials missing from environment.")
        
        return S3Storage(S3_BUCKET, AWS_REGION, access_key, secret_key, prefix=S3_PREFIX)
    else:
        # Local Storage (Fallback)
        # Serving files: We need to match Flask's STATIC serving or a dedicated Route.
        return LocalStorage(INSTANCE_DIR, f"{BASE_URL}") 
