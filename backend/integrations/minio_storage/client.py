# Custom libraries
from logger import configure_logging

# Default libraries
import os
from typing import Optional

# Installed libraries
from dotenv import load_dotenv
from minio import Minio


load_dotenv()

logger = configure_logging(__name__)


class MinIOStorage:
    """
    Handles operations for interacting with MinIO object storage.
    """

    def __init__(self, data_store=None):
        """
        Initializes MinIOStorage with data store configurations.
        Reads MinIO endpoint, credentials, and bucket from environment (or data_store for bucket).

        Args:
            data_store: Data store configurations (storage_bucket overrides env bucket if set)
        """
        self.data_store = data_store or {}
        self.endpoint = os.getenv("MINIO_ENDPOINT", "minio:9000")
        self.access_key = os.getenv("MINIO_ACCESS_KEY", "")
        self.secret_key = os.getenv("MINIO_SECRET_KEY", "")
        self.secure = os.getenv("MINIO_SECURE", "false").lower() == "true"
        self.default_bucket = os.getenv("MINIO_KNOWLEDGE_BUCKET", "assistcx-knowledge")
        self.bucket = self.data_store.get("storage_bucket") or self.default_bucket
        self._client = None

    def _get_client(self) -> Optional[Minio]:
        """
        Returns a MinIO client instance from environment configuration.

        Returns:
            Optional[Minio]: MinIO client, None if credentials are missing or creation fails.
        """
        if not self.access_key or not self.secret_key:
            logger.error("MINIO_ACCESS_KEY and MINIO_SECRET_KEY must be set")
            return None
        if self._client is None:
            try:
                self._client = Minio(
                    self.endpoint,
                    access_key=self.access_key,
                    secret_key=self.secret_key,
                    secure=self.secure,
                )
            except Exception as e:
                logger.error(f"Failed to create MinIO client: {e}")
                return None
        return self._client

    def _normalize_key(self, mounted_path: str) -> Optional[str]:
        """
        Normalizes an object key from a mounted path (strip leading slash and bucket prefix).

        Args:
            mounted_path: Object key (path) in the bucket, optionally including bucket name prefix.

        Returns:
            Optional[str]: Normalized key, or None if path is empty after stripping.
        """
        if not mounted_path or not isinstance(mounted_path, str):
            return None
        key = mounted_path.strip().lstrip("/")
        if key.startswith(self.bucket + "/"):
            key = key[len(self.bucket) + 1 :]
        return key if key else None

    def _ensure_bucket(self) -> bool:
        """
        Ensures the configured bucket exists; creates it if not.

        Returns:
            bool: True if bucket is available, False on failure.
        """
        client = self._get_client()
        if not client:
            return False
        try:
            if not client.bucket_exists(self.bucket):
                client.make_bucket(self.bucket)
                logger.info(f"Created MinIO bucket: {self.bucket}")
            return True
        except Exception as e:
            logger.error(f"Failed to ensure bucket {self.bucket}: {e}")
            return False

    def upload_file(self, source_path: str, destination_path: str) -> Optional[str]:
        """
        Uploads a file from the local file system and returns the object path (key).

        Args:
            source_path: Local path to the file to upload.
            destination_path: Object key (path) in the bucket.

        Returns:
            Optional[str]: Object path (key) of the uploaded file, None if failed.
        """
        if not source_path or not destination_path:
            logger.error("source_path and destination_path are required")
            return None
        key = self._normalize_key(destination_path)
        if key is None:
            logger.error("destination_path is invalid or empty")
            return None
        try:
            client = self._get_client()
            if not client:
                return None
            if not self._ensure_bucket():
                return None
            client.fput_object(self.bucket, key, source_path)
            logger.info(f"File saved to MinIO path {self.bucket}/{key}")
            return key
        except FileNotFoundError:
            logger.error(f"The file {source_path} was not found.")
            return None
        except Exception as e:
            logger.error(f"Unexpected error during file upload: {str(e)}")
            return None

    def delete_file(self, mounted_path: str) -> bool:
        """
        Deletes a file from the specified MinIO object path (key).

        Args:
            mounted_path: Object key (path) of the file to delete.

        Returns:
            bool: True if file was deleted successfully or not found, False on error.
        """
        key = self._normalize_key(mounted_path)
        if key is None:
            logger.error("mounted_path is invalid or empty")
            return False
        try:
            client = self._get_client()
            if not client:
                return False
            client.remove_object(self.bucket, key)
            logger.info(f"File deleted from MinIO path {self.bucket}/{key}")
            return True
        except Exception as e:
            logger.error(f"Unexpected error during file delete: {str(e)}")
            return False

    def download_file(self, mounted_path: str, local_directory: str) -> Optional[str]:
        """
        Downloads a file from the specified MinIO object path and returns the local path.

        Args:
            mounted_path: Object key (path) in the bucket.
            local_directory: Local directory to save the file into.

        Returns:
            Optional[str]: Full path to the saved file, None if failed.
        """
        key = self._normalize_key(mounted_path)
        if key is None:
            logger.error("mounted_path is invalid or empty")
            return None
        if not local_directory:
            logger.error("local_directory is required")
            return None
        try:
            client = self._get_client()
            if not client:
                return None
            filename = os.path.basename(key) or "download"
            destination = os.path.join(local_directory, filename)
            os.makedirs(local_directory, exist_ok=True)
            client.fget_object(self.bucket, key, destination)
            logger.info(f"Downloaded {self.bucket}/{key} to {destination}")
            return destination
        except FileNotFoundError:
            logger.error(
                f"The object at {mounted_path} or directory {local_directory} was not found."
            )
            return None
        except Exception as e:
            logger.error(f"Unexpected error during file download: {str(e)}")
            return None

    def get_object(self, mounted_path: str) -> Optional[bytes]:
        """
        Reads an object from MinIO and returns its content as bytes.
        Used when the caller needs in-memory content (e.g. document_file.download_file for local).

        Args:
            mounted_path: Object key (path) in the bucket.

        Returns:
            Optional[bytes]: Object content if successful, None if failed.
        """
        key = self._normalize_key(mounted_path)
        if key is None:
            logger.error("mounted_path is invalid or empty")
            return None
        try:
            client = self._get_client()
            if not client:
                return None
            response = client.get_object(self.bucket, key)
            try:
                return response.read()
            finally:
                response.close()
                response.release_conn()
        except Exception as e:
            logger.error(f"Unexpected error reading object {mounted_path}: {str(e)}")
            return None
