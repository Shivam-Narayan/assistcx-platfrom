# Custom libraries
from configs.auth_schemas_v4 import AUTH_SCHEMAS
from logger import configure_logging
from models.connection_v4 import Connection
from utils.crypto_utils import decrypt_string


# Database modules
from repository.connection_repository_v4 import ConnectionRepository
from utils.schema_utils import async_db_pool

# Default libraries
import os
import tempfile
from typing import Dict, List, Optional, Tuple, Union
from uuid import UUID
from urllib.parse import urlparse
import asyncio
import json
import mimetypes

# Installed libraries
from botocore.client import Config
from botocore.exceptions import ClientError, NoCredentialsError
from sqlalchemy.ext.asyncio import AsyncSession
import boto3


logger = configure_logging(__name__)


class AWSS3V4:
    """
    Handles AWS S3 operations using connection-based credentials (v4).
    Resolves connection from tool_runtime, extracts credentials from encrypted_credentials,
    and runs S3 calls asynchronously.
    """

    def __init__(
        self,
        db: AsyncSession,
        organization_schema: Optional[str] = None,
        data_store: Optional[dict] = None,
    ):
        """
        Initializes AWSS3V4 with database session and optional storage config.

        Args:
            db: Async database session for resolving connections
            organization_schema: Optional organization schema (used globally where needed)
            data_store: Optional storage config (bucket, folder, region). When set, methods use self.data_store;
                otherwise fall back to tool_runtime.get("data_store").
        """
        self.db = db
        self.organization_schema = organization_schema
        self.data_store = data_store

    async def resolve_connection(self, tool_runtime: dict) -> Optional[Connection]:
        """
        Resolves connection from tool runtime (tool_action + tool_connections or connection_id).

        Args:
            tool_runtime: Runtime configuration containing tool_action, tool_connections, connection_id

        Returns:
            Optional[Connection]: Resolved connection or None if not found
        """
        try:
            tool_action = tool_runtime.get("tool_action")
            tool_connections = tool_runtime.get("tool_connections", {})
            connection_id = tool_connections.get(tool_action) if tool_action else None
            if not connection_id:
                connection_id = tool_runtime.get("connection_id")
            if not connection_id:
                return None

            connection_repository = ConnectionRepository(self.db)
            connection = await connection_repository.get_connection_by_id(
                UUID(connection_id) if isinstance(connection_id, str) else connection_id
            )
            if (
                connection
                and connection.is_active
                and connection.auth_status == "valid"
            ):
                return connection
            return None
        except Exception as e:
            logger.error(f"Error resolving connection: {e}")
            return None

    def _get_credentials_from_connection(
        self, connection: Connection
    ) -> Optional[Dict[str, str]]:
        """
        Extracts and decrypts credentials from connection using auth schema.

        Args:
            connection: Connection with encrypted_credentials and auth_schema_key

        Returns:
            Optional[Dict]: Decrypted credentials dict keyed by auth schema input_fields, or None
        """
        try:
            raw_credentials = json.loads(connection.encrypted_credentials)
            if not raw_credentials:
                logger.error("No encrypted credentials found in connection")
                return None

            auth_schema = AUTH_SCHEMAS.get(connection.auth_schema_key)
            if not auth_schema:
                logger.warning(f"Unknown auth_schema_key: {connection.auth_schema_key}")
                return None

            input_fields = auth_schema.get("input_fields", {})
            credentials = {}
            for field_key in input_fields:
                raw_value = raw_credentials.get(field_key)
                credentials[field_key] = (
                    decrypt_string(raw_value) if raw_value else None
                )

            for field_key, field_def in input_fields.items():
                if field_def.get("required") and not credentials.get(field_key):
                    logger.error("Missing required credential fields in connection")
                    return None
            return credentials

        except json.JSONDecodeError as e:
            logger.error(f"Invalid encrypted_credentials JSON for connection: {e}")
            return None
        except Exception as e:
            logger.error(f"Error extracting credentials: {e}", exc_info=True)
            return None

    def _get_s3_client(
        self,
        connection: Connection,
        region: Optional[str] = None,
    ) -> Optional[boto3.client]:
        """
        Creates a boto3 S3 client from decrypted credentials (sync).

        Args:
            credentials: Dict with AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
            region: Optional region for the client

        Returns:
            boto3 S3 client or None
        """
        try:
            credentials = self._get_credentials_from_connection(connection)
            if not credentials:
                logger.error("No AWS credentials found.")
                return None
            client_kwargs = {
                "aws_access_key_id": credentials["AWS_ACCESS_KEY_ID"],
                "aws_secret_access_key": credentials["AWS_SECRET_ACCESS_KEY"],
                "config": Config(signature_version="s3v4"),
            }
            if region:
                client_kwargs["region_name"] = region
            return boto3.client("s3", **client_kwargs)
        except Exception as e:
            logger.error(f"Failed to create S3 client: {e}", exc_info=True)
            return None

    def _normalize_json_strings(
        self, data: Union[dict, list, str]
    ) -> Union[dict, list, str]:
        """
        Recursively process all string values in the given data to normalize the data.
        Parse strings to handle escape characters and preserve its native JSON type (list or dict).

        Args:
            data: Data to normalize

        Returns:
            Union[dict, list, str]: Normalized data
        """
        if isinstance(data, dict):
            return {k: self._normalize_json_strings(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._normalize_json_strings(item) for item in data]
        elif isinstance(data, str):
            try:
                # Try parsing the string to see if it's embedded JSON
                parsed = json.loads(data)
                # Return the parsed JSON if successful (could be a list or dict)
                return self._normalize_json_strings(parsed)
            except json.JSONDecodeError:
                # It's not JSON, return as is
                return data
        else:
            return data

    async def delete_file(
        self,
        connection: Connection,
        s3_url: str,
    ) -> bool:
        """
        Deletes a file from the specified AWS S3 URL.

        Args:
            s3_url: S3 URL of the file to delete

        Returns:
            bool: True if file was deleted successfully, False otherwise
        """
        try:
            bucket_name = self.data_store.get("storage_bucket")
            if not bucket_name:
                logger.error("storage_bucket not configured in data_store")
                return False
            key = urlparse(s3_url).path.lstrip("/")

            s3_client = self._get_s3_client(connection)
            if s3_client is None:
                return False

            # Check if the object exists before attempting to delete
            try:
                await asyncio.to_thread(
                    lambda: s3_client.head_object(Bucket=bucket_name, Key=key)
                )
            except ClientError as e:
                # If a 404 error is raised, the object does not exist
                if e.response["Error"]["Code"] == "404":
                    logger.warning(f"File not found in S3 bucket: {key}")
                    return True
                raise

            # If we've made it here, the object exists - proceed with deletion
            await asyncio.to_thread(
                lambda: s3_client.delete_object(Bucket=bucket_name, Key=key)
            )
            logger.info(f"File deleted from S3 bucket: {s3_url}")
            return True
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            logger.error(f"S3 Client Error: {error_code} - {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during file delete: {str(e)}")
            return False

    async def generate_presigned_url(
        self,
        connection: Connection,
        aws_s3_path: str,
        expiration: int = 3600,
    ) -> Optional[str]:
        """
        Generates a presigned URL to share an AWS S3 object.

        Args:
            aws_s3_path: AWS S3 path of the object
            expiration: Expiration time in seconds

        Returns:
            Optional[str]: Presigned URL to share the AWS S3 object, None if failed
        """
        try:
            # Parse the S3 bucket path to extract bucket name and file path
            parsed_url = urlparse(aws_s3_path, allow_fragments=False)
            s3_file_path = parsed_url.path.lstrip("/")
            bucket = urlparse(aws_s3_path).hostname.split(".")[0]
            region = urlparse(aws_s3_path).hostname.split(".")[2]

            s3_client = self._get_s3_client(connection, region)
            if s3_client is None:
                return None

            def _gen():
                return s3_client.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": bucket, "Key": s3_file_path},
                    ExpiresIn=expiration,
                )

            response = await asyncio.to_thread(_gen)
            return response
        except Exception as e:
            logger.error(f"Error generating presigned URL: {str(e)}")
            return None

    async def get_bucket_region(
        self,
        connection: Connection,
        bucket_name: str,
    ) -> Optional[str]:
        """
        Returns the AWS region where the given bucket is hosted.
        Defaults to 'us-east-1' if the region is not specified by AWS.

        Args:
            bucket_name: Name of the bucket

        Returns:
            Optional[str]: AWS region where the bucket is hosted, None if failed
        """
        try:
            s3_client = self._get_s3_client(connection)
            if s3_client is None:
                return None

            # Get the bucket location and rerieve the region
            def _location():
                return s3_client.get_bucket_location(Bucket=bucket_name)

            location = await asyncio.to_thread(_location)
            region = location["LocationConstraint"]

            # If the region is None, it means the bucket is in us-east-1
            if region is None:
                region = "us-east-1"

            logger.info(f"The bucket '{bucket_name}' is in the region: {region}")
            return region
        except Exception as e:
            logger.error(f"Error determining bucket region: {str(e)}")
            return None

    async def copy_email_data(
        self,
        connection: Connection,
        upload_data: dict,
    ) -> Optional[str]:
        """
        Uploads the email data to the AWS S3 bucket and returns the S3 URL.

        Args:
            upload_data: Email data to upload

        Returns:
            Optional[str]: S3 URL of the uploaded email data, None if failed
        """
        processed_data = self._normalize_json_strings(upload_data)
        file_content = json.dumps(processed_data, ensure_ascii=False, default=str)
        content_type = "application/json"
        file_extension = ".json"

        # Prepare file name and destination path
        datetime = upload_data["received_at"].strftime("%Y%m%d_%H%M%S")
        file_name = f"{datetime}_{upload_data['email_id']}"
        base_name = file_name.rsplit(".", 1)[0]  # Remove extension if it exists
        base_name = base_name.replace(".", "")  # Remove all remaining dots
        file_name_with_extension = f"{base_name}{file_extension}"
        destination_path = (
            f"{self.data_store.get('storage_folder', '').rstrip('/')}/{file_name_with_extension}"
            if self.data_store.get("storage_folder")
            else file_name_with_extension
        )

        try:
            s3_client = self._get_s3_client(connection)
            bucket_name = self.data_store.get("storage_bucket")
            if not bucket_name:
                logger.error("storage_bucket not configured in data_store")
                return None

            def _put():
                s3_client.put_object(
                    Body=file_content.encode("utf-8"),
                    Bucket=bucket_name,
                    Key=destination_path,
                    ContentType=content_type,
                )

            await asyncio.to_thread(_put)
            logger.info(
                f"Data uploaded to S3 bucket {bucket_name} in folder {self.data_store.get('storage_folder', '')}"
            )
            s3_url = f"https://{bucket_name}.s3.amazonaws.com/{destination_path}"
            logger.info(f"File uploaded to {s3_url}")
            return s3_url
        except NoCredentialsError:
            logger.error("No AWS credentials found.")
            return None
        except Exception as e:
            logger.error(f"Failed to upload data: {str(e)}")
            return None

    async def upload_data(
        self,
        connection: Connection,
        file_content: bytes,
        file_type: str,
        destination_path: str,
    ) -> Optional[str]:
        """
        Uploads file content to S3 (runs blocking boto3 in thread). Returns S3 URL or None.
        """
        region = self.data_store.get("storage_region")
        bucket_name = self.data_store.get("storage_bucket")
        if not bucket_name:
            logger.error("storage_bucket not configured in data_store")
            return None

        s3_client = self._get_s3_client(connection, region)
        if not s3_client:
            return None

        def _put():
            s3_client.put_object(
                Body=file_content,
                Bucket=bucket_name,
                Key=destination_path,
                ContentType=file_type,
            )

        try:
            await asyncio.to_thread(_put)
            storage_region = self.data_store.get("storage_region", "")
            s3_url = (
                f"https://{bucket_name}.s3.{storage_region}.amazonaws.com/{destination_path}"
                if storage_region
                else f"https://{bucket_name}.s3.amazonaws.com/{destination_path}"
            )
            logger.info(f"File uploaded to {s3_url}")
            return s3_url

        except NoCredentialsError:
            logger.error("No AWS credentials found.")
            return None
        except ClientError as e:
            logger.error(
                "S3 error during upload: %s", e.response.get("Error", {}).get("Code")
            )
            return None
        except Exception as e:
            logger.error("Failed to upload: %s", e, exc_info=True)
            return None

    async def upload_file(
        self,
        connection: Connection,
        source_path: str,
        destination_path: str,
    ) -> Optional[str]:
        """
        Uploads a local file to S3 (runs blocking boto3 in thread). Returns S3 URL or None.
        """
        region = self.data_store.get("storage_region")
        bucket_name = self.data_store.get("storage_bucket")
        if not bucket_name:
            logger.error("storage_bucket not configured in data_store")
            return None

        s3_client = self._get_s3_client(connection, region)
        if not s3_client:
            return None

        def _upload():
            s3_client.upload_file(source_path, bucket_name, destination_path)

        try:
            await asyncio.to_thread(_upload)
            storage_region = self.data_store.get("storage_region", "")
            s3_url = (
                f"https://{bucket_name}.s3.{storage_region}.amazonaws.com/{destination_path}"
                if storage_region
                else f"https://{bucket_name}.s3.amazonaws.com/{destination_path}"
            )
            logger.info(f"File uploaded to {s3_url}")
            return s3_url

        except FileNotFoundError:
            logger.error("File not found: %s", source_path)
            return None
        except NoCredentialsError:
            logger.error("No AWS credentials found.")
            return None
        except ClientError as e:
            logger.error(
                "S3 error during upload: %s", e.response.get("Error", {}).get("Code")
            )
            return None
        except Exception as e:
            logger.error("Failed to upload file: %s", e, exc_info=True)
            return None

    async def upload_fileobj(
        self,
        connection: Connection,
        file_obj,
        s3_path: str,
    ) -> Optional[str]:
        """
        Uploads a file-like object and returns the file's S3 URL.

        Args:
            file_obj: File-like object to upload
            s3_path: Path to the destination file

        Returns:
            Optional[str]: S3 URL of the uploaded file, None if failed
        """
        try:
            s3_client = self._get_s3_client(connection)
            if s3_client is None:
                return None
            bucket_name = self.data_store.get("storage_bucket")
            if not bucket_name:
                logger.error("storage_bucket not configured in data_store")
                return None

            def _upload_obj():
                s3_client.upload_fileobj(file_obj, bucket_name, s3_path)

            await asyncio.to_thread(_upload_obj)
            s3_url = f"https://{bucket_name}.s3.amazonaws.com/{s3_path}"
            logger.info(f"File uploaded directly to S3: {s3_url}")
            return s3_url
        except FileNotFoundError:
            logger.error(
                "The file object could not be uploaded because it was not found."
            )
        except NoCredentialsError:
            logger.error("AWS credentials not available for S3 upload.")
        except Exception as e:
            logger.error(f"Unexpected error during file upload: {str(e)}")
        return None

    async def _resolve_tool_context(
        self, tool_runtime: dict
    ) -> Tuple[Optional[Connection], Optional[str]]:
        """
        Shared preamble for tool wrapper methods. Validates data_store, storage_bucket,
        and resolves connection from tool_runtime.

        Args:
            tool_runtime: Runtime with tool_action, tool_connections/connection_id

        Returns:
            Tuple[Optional[Connection], Optional[str]]: (connection, error_json).
                If error_json is not None, return it immediately from the caller.
        """
        if not self.data_store:
            return None, json.dumps(
                {
                    "status_code": 400,
                    "message": "Missing data_store. Set via init or in tool_runtime.",
                },
                ensure_ascii=False,
            )
        if not self.data_store.get("storage_bucket"):
            return None, json.dumps(
                {
                    "status_code": 400,
                    "message": "storage_bucket not configured in data_store",
                },
                ensure_ascii=False,
            )
        connection = await self.resolve_connection(tool_runtime)
        if not connection:
            return None, json.dumps(
                {
                    "status_code": 400,
                    "message": "No connection bound for this tool. Create a tool binding or ensure task has connection context.",
                },
                ensure_ascii=False,
            )
        return connection, None

    async def download_file(
        self,
        tool_runtime: dict,
        remote_path: str,
        local_path: Optional[str] = None,
    ) -> str:
        """
        Downloads a file from AWS S3.

        Args:
            tool_runtime: Runtime with tool_action, tool_connections/connection_id, data_store
            remote_path: S3 URL or path of the file in S3
            local_path: Optional local path to save the downloaded file

        Returns:
            str: JSON string with status_code and message
        """
        if not tool_runtime or not remote_path or not remote_path.strip():
            return json.dumps(
                {
                    "status_code": 400,
                    "message": "Missing required parameters: tool_runtime and remote_path are required",
                },
                ensure_ascii=False,
            )

        connection, error = await self._resolve_tool_context(tool_runtime)
        if error:
            return error

        # Create S3 client
        region = self.data_store.get("storage_region")
        s3_client = self._get_s3_client(connection, region)
        if not s3_client:
            return json.dumps(
                {"status_code": 500, "message": "Failed to create S3 client"},
                ensure_ascii=False,
            )

        # Parse S3 path/URL
        if remote_path.startswith("https://"):
            parsed_url = urlparse(remote_path)
            bucket_name = parsed_url.netloc.split(".")[0]
            s3_path = parsed_url.path.lstrip("/")
        else:
            s3_path = remote_path.lstrip("/")

        # Download file from S3
        def _get():
            response = s3_client.get_object(Bucket=bucket_name, Key=s3_path)
            content = response["Body"].read()
            content_type = (
                response.get("ContentType")
                or mimetypes.guess_type(s3_path)[0]
                or "application/octet-stream"
            )
            return content, content_type

        # Download file
        try:
            content, content_type = await asyncio.to_thread(_get)
            logger.info("File downloaded from S3: s3://%s/%s", bucket_name, s3_path)

            if local_path:
                local_dir = os.path.dirname(local_path)
                if local_dir:
                    os.makedirs(local_dir, exist_ok=True)

                # Write file to local path
                def _write():
                    with open(local_path, "wb") as f:
                        f.write(content)

                await asyncio.to_thread(_write)
                logger.info("File saved to local path: %s", local_path)
                return json.dumps(
                    {
                        "status_code": 200,
                        "message": f"File downloaded and saved to local path: {local_path}",
                    },
                    ensure_ascii=False,
                )

            # Return file content info
            return json.dumps(
                {
                    "status_code": 200,
                    "message": "File downloaded successfully",
                    "data": {
                        "content_length": len(content),
                        "content_type": content_type,
                    },
                },
                ensure_ascii=False,
            )

        except NoCredentialsError:
            logger.error("No AWS credentials found")
            return json.dumps(
                {"status_code": 401, "message": "No AWS credentials found"},
                ensure_ascii=False,
            )
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            if error_code == "NoSuchKey":
                bucket_info = f"s3://{bucket_name}/{s3_path}"
                logger.error("File not found: %s", bucket_info)
                return json.dumps(
                    {
                        "status_code": 404,
                        "message": f"File not found: {bucket_info}",
                    },
                    ensure_ascii=False,
                )
            logger.error("AWS S3 error in download_file: %s", e)
            return json.dumps(
                {
                    "status_code": 500,
                    "message": f"Failed to download file: {str(e)}",
                },
                ensure_ascii=False,
            )
        except Exception as e:
            logger.error("Unexpected error in download_file: %s", e, exc_info=True)
            return json.dumps(
                {
                    "status_code": 500,
                    "message": f"Failed to download file from S3: {str(e)}",
                },
                ensure_ascii=False,
            )

    async def tool_upload_file(
        self,
        tool_runtime: dict,
        source_path: str,
        file_name: str,
    ) -> str:
        """
        Tool wrapper for uploading a local file to S3.

        Args:
            tool_runtime: Runtime with tool_action, tool_connections/connection_id
            source_path: Local path of the file to upload
            file_name: Name of the file in the S3 bucket

        Returns:
            str: JSON string with status_code and message
        """
        if (
            not tool_runtime
            or not source_path
            or not source_path.strip()
            or not file_name
            or not file_name.strip()
        ):
            return json.dumps(
                {
                    "status_code": 400,
                    "message": "Missing required parameters: tool_runtime, source_path, and file_name are required",
                },
                ensure_ascii=False,
            )

        connection, error = await self._resolve_tool_context(tool_runtime)
        if error:
            return error

        try:
            # Prepare file path: remove extension, clean dots, preserve source extension
            base_name = file_name.rsplit(".", 1)[0].replace(".", "")
            source_ext = source_path.rsplit(".", 1)[-1] if "." in source_path else ""
            file_extension = f".{source_ext}" if source_ext else ""
            file_name_with_extension = f"{base_name}{file_extension}"
            data_folder = self.data_store.get("storage_folder", "").rstrip("/")
            destination_path = (
                f"{data_folder}/{file_name_with_extension}"
                if data_folder
                else file_name_with_extension
            )

            result = await self.upload_file(
                connection=connection,
                source_path=source_path,
                destination_path=destination_path,
            )

            if result:
                logger.info(f"File uploaded successfully: {result}")
                return json.dumps(
                    {
                        "status_code": 200,
                        "message": f"File uploaded successfully: {result}",
                    },
                    ensure_ascii=False,
                )
            logger.error("Failed to upload file: AWS S3 returned None")
            return json.dumps(
                {"status_code": 500, "message": "Failed to upload file"},
                ensure_ascii=False,
            )

        except FileNotFoundError:
            logger.error(f"File not found: {source_path}")
            return json.dumps(
                {"status_code": 404, "message": f"File not found: {source_path}"},
                ensure_ascii=False,
            )
        except NoCredentialsError:
            logger.error("No AWS credentials found.")
            return json.dumps(
                {"status_code": 401, "message": "No AWS credentials found"},
                ensure_ascii=False,
            )
        except Exception as e:
            logger.error(f"Failed to upload file: {e}", exc_info=True)
            return json.dumps(
                {
                    "status_code": 500,
                    "message": f"Failed to upload file: {str(e)}",
                },
                ensure_ascii=False,
            )

    async def tool_upload_structured_data(
        self,
        tool_runtime: dict,
        data: Union[Dict, List[Dict]],
        file_name: str,
    ) -> str:
        """
        Tool wrapper for uploading structured data (JSON) to S3.

        Args:
            tool_runtime: Runtime with tool_action, tool_connections/connection_id
            data: Structured data (dict or list of dicts) to upload as JSON
            file_name: Name of the file to create

        Returns:
            str: JSON string with status_code and message
        """
        if not tool_runtime or data is None or not file_name or not file_name.strip():
            return json.dumps(
                {
                    "status_code": 400,
                    "message": "Missing required parameters: tool_runtime, data, and file_name are required",
                },
                ensure_ascii=False,
            )

        if isinstance(data, list) and not all(isinstance(item, dict) for item in data):
            return json.dumps(
                {
                    "status_code": 400,
                    "message": "data list must contain only dictionaries",
                },
                ensure_ascii=False,
            )

        connection, error = await self._resolve_tool_context(tool_runtime)
        if error:
            return error

        try:
            processed_data = self._normalize_json_strings(data)
            file_content = json.dumps(processed_data, ensure_ascii=False).encode(
                "utf-8"
            )

            base_name = file_name.rsplit(".", 1)[0].replace(".", "")
            file_name_with_extension = f"{base_name}.json"
            data_folder = self.data_store.get("storage_folder", "").rstrip("/")
            destination_path = (
                f"{data_folder}/{file_name_with_extension}"
                if data_folder
                else file_name_with_extension
            )

            result = await self.upload_data(
                connection=connection,
                file_content=file_content,
                file_type="application/json",
                destination_path=destination_path,
            )

            if result:
                logger.info(f"Structured data uploaded successfully: {result}")
                return json.dumps(
                    {
                        "status_code": 200,
                        "message": f"Structured data uploaded successfully: {result}",
                    },
                    ensure_ascii=False,
                )

            return json.dumps(
                {"status_code": 500, "message": "Failed to upload structured data"},
                ensure_ascii=False,
            )

        except NoCredentialsError:
            logger.error("No AWS credentials found.")
            return json.dumps(
                {"status_code": 401, "message": "No AWS credentials found"},
                ensure_ascii=False,
            )
        except Exception as e:
            logger.error(f"Failed to upload structured data: {e}", exc_info=True)
            return json.dumps(
                {
                    "status_code": 500,
                    "message": f"Failed to upload structured data: {str(e)}",
                },
                ensure_ascii=False,
            )

    async def tool_upload_text_data(
        self,
        tool_runtime: dict,
        data: str,
        file_name: str,
    ) -> str:
        """
        Tool wrapper for uploading plain text data to S3 as .txt files.

        Args:
            tool_runtime: Runtime with tool_action, tool_connections/connection_id
            data: Text data to upload
            file_name: Name of the file to create

        Returns:
            str: JSON string with status_code and message
        """
        if not tool_runtime or data is None or not file_name or not file_name.strip():
            return json.dumps(
                {
                    "status_code": 400,
                    "message": "Missing required parameters: tool_runtime, data, and file_name are required",
                },
                ensure_ascii=False,
            )

        connection, error = await self._resolve_tool_context(tool_runtime)
        if error:
            return error

        try:
            file_content = str(data).encode("utf-8")

            base_name = file_name.rsplit(".", 1)[0].replace(".", "")
            file_name_with_extension = f"{base_name}.txt"
            data_folder = self.data_store.get("storage_folder", "").rstrip("/")
            destination_path = (
                f"{data_folder}/{file_name_with_extension}"
                if data_folder
                else file_name_with_extension
            )

            result = await self.upload_data(
                connection=connection,
                file_content=file_content,
                file_type="text/plain",
                destination_path=destination_path,
            )

            if result:
                logger.info(f"Text data uploaded successfully: {result}")
                return json.dumps(
                    {
                        "status_code": 200,
                        "message": f"Text data uploaded successfully: {result}",
                    },
                    ensure_ascii=False,
                )
            logger.error("Failed to upload text data: AWS S3 returned None")
            return json.dumps(
                {"status_code": 500, "message": "Failed to upload text data"},
                ensure_ascii=False,
            )
        except NoCredentialsError:
            logger.error("No AWS credentials found.")
            return json.dumps(
                {"status_code": 401, "message": "No AWS credentials found"},
                ensure_ascii=False,
            )
        except Exception as e:
            logger.error(f"Failed to upload text data: {e}", exc_info=True)
            return json.dumps(
                {
                    "status_code": 500,
                    "message": f"Failed to upload text data: {str(e)}",
                },
                ensure_ascii=False,
            )


class AWSS3V4Validator:
    @staticmethod
    async def validate_credentials(credentials: Dict) -> Tuple[bool, Optional[str]]:
        """
        Validates S3 Bucket credentials by attempting to list buckets.
        Returns a tuple of (is_valid, error_message).
        Runs blocking boto3 call in a thread so it is non-blocking.
        """
        # Check if all required fields are present
        required_fields = ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"]
        for field in required_fields:
            if field not in credentials:
                return False, f"Missing required field: {field}"
        try:

            def _list_buckets():
                client_kwargs = {
                    "aws_access_key_id": credentials["AWS_ACCESS_KEY_ID"],
                    "aws_secret_access_key": credentials["AWS_SECRET_ACCESS_KEY"],
                    "config": Config(signature_version="s3v4"),
                }
                s3_client = boto3.client("s3", **client_kwargs)
                s3_client.list_buckets()

            await asyncio.to_thread(_list_buckets)
            return True, None

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_message = e.response.get("Error", {}).get("Message", str(e))
            return False, f"S3 Bucket validation failed: {error_code} {error_message}"

        except NoCredentialsError:
            return False, "No credentials provided or credentials are invalid"

        except Exception as e:
            return False, f"Error validating S3 Bucket credentials: {str(e)}"


if __name__ == "__main__":
    CONNECTION_ID = "1b9884ce-7f3a-49fd-8b49-935806d9ca25"
    DATA_STORE = {
        "storage_bucket": "assistcx-data",
        "storage_folder": "data",
        "storage_region": "ap-south-1",
    }
    # For validator test: set your AWS keys here (or use dummy to see validation error)
    AWS_ACCESS_KEY_ID = ""
    AWS_SECRET_ACCESS_KEY = ""

    async def run_tests():
        tool_runtime_base = {"organization_schema": "public"}

        async with async_db_pool.get_session("public") as db_session:
            aws_s3 = AWSS3V4(db=db_session, data_store=DATA_STORE)

            # Test 1: tool_upload_structured_data
            print("\n--- Testing tool_upload_structured_data ---")
            result = await aws_s3.tool_upload_structured_data(
                tool_runtime={
                    **tool_runtime_base,
                    "tool_action": "aws_s3_upload_structured_data",
                    "tool_connections": {
                        "aws_s3_upload_structured_data": CONNECTION_ID
                    },
                },
                data={"key": "value", "nested": {"a": 1}},
                file_name="test_upload.json",
            )
            print(result)

            # Test 2: tool_upload_text_data
            print("\n--- Testing tool_upload_text_data ---")
            result = await aws_s3.tool_upload_text_data(
                tool_runtime={
                    **tool_runtime_base,
                    "tool_action": "aws_s3_upload_text_data",
                    "tool_connections": {"aws_s3_upload_text_data": CONNECTION_ID},
                },
                data="Hello, this is plain text content.",
                file_name="test_upload.txt",
            )
            print(result)

            # Test 3: tool_upload_file (create a temp file so test is self-contained)
            print("\n--- Testing tool_upload_file ---")
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False, prefix="aws_s3_v4_"
            ) as tmp:
                tmp.write("Test content for S3 file upload.\n")
                tmp_path = tmp.name
            try:
                result = await aws_s3.tool_upload_file(
                    tool_runtime={
                        **tool_runtime_base,
                        "tool_action": "aws_s3_upload_file",
                        "tool_connections": {"aws_s3_upload_file": CONNECTION_ID},
                    },
                    source_path=tmp_path,
                    file_name="uploaded_file.txt",
                )
                print(result)
            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

            # Test 4: tool_download_file (use an existing S3 URL or key from your bucket)
            print("\n--- Testing tool_download_file ---")
            result = await aws_s3.download_file(
                tool_runtime={
                    **tool_runtime_base,
                    "tool_action": "aws_s3_download_file",
                    "tool_connections": {"aws_s3_download_file": CONNECTION_ID},
                },
                remote_path=f"https://assistcx-data.s3.ap-south-1.amazonaws.com/data/test_upload.json",
                local_path=None,  # or e.g. "/tmp/downloaded.json"
            )
            print(result)

        # Test 5: AWSS3V4Validator.validate_credentials
        print("\n--- Testing AWSS3V4Validator.validate_credentials ---")
        result = await AWSS3V4Validator.validate_credentials(
            {
                "AWS_ACCESS_KEY_ID": AWS_ACCESS_KEY_ID,
                "AWS_SECRET_ACCESS_KEY": AWS_SECRET_ACCESS_KEY,
            }
        )
        print(result)

    asyncio.run(run_tests())
