# Custom libraries
from logger import configure_logging
from utils.crypto_utils import decrypt_string
from utils.environment import environment

# Default libraries
from typing import Dict, List, Optional, Tuple, Union
import json
import mimetypes
import os

# Installed libraries
from botocore.client import Config
from botocore.exceptions import ClientError, NoCredentialsError
from dotenv import load_dotenv
from urllib.parse import urlparse
import boto3
import requests


load_dotenv()

logger = configure_logging(__name__)


class AWSS3:
    """
    Handles operations for interacting with AWS S3.
    """

    def __init__(self, organization_schema, data_store=None):
        """
        Initializes AWSS3 with organization schema and data store configurations.

        Args:
            organization_schema: Organization schema
            data_store: Data store configurations
        """
        self.organization_schema = organization_schema
        self.data_store = data_store
        self._s3_client = None
        self._org_env = environment.get_environment(self.organization_schema)

    @property
    def s3(self):
        if self._s3_client is None:
            self._s3_client = self._get_s3_client()
        return self._s3_client

    def _get_s3_client(self, region: Optional[str] = None) -> Optional[boto3.client]:
        """
        Creates a boto3 S3 client using the organization credentials and the specified region.

        Args:
            region: Optional region to use for the S3 client

        Returns:
            Optional[boto3.client]: S3 client, None if failed
        """
        try:
            if self._org_env is None:
                logger.error(f"Missing organization environment for: {self.organization_schema}")
                return None

            credentials = self._org_env.get("AWS_S3")
            if not credentials:
                logger.error(
                    f"Missing AWS_S3 credentials for: {self.organization_schema}"
                )
                return None
            aws_access_key_id = credentials.get("AWS_ACCESS_KEY_ID")
            aws_secret_access_key = credentials.get("AWS_SECRET_ACCESS_KEY")

            # Use data_store for bucket region if not provided
            if region is None:
                region = self.data_store.get("storage_region")

            if aws_access_key_id and aws_secret_access_key:
                client_kwargs = {
                    "aws_access_key_id": decrypt_string(aws_access_key_id),
                    "aws_secret_access_key": decrypt_string(aws_secret_access_key),
                    "config": Config(signature_version="s3v4"),
                }
                if region:
                    client_kwargs["region_name"] = region
                return boto3.client("s3", **client_kwargs)
            else:
                logger.error(f"Missing AWS credentials for: {self.organization_schema}")
                return None
        except Exception as e:
            logger.error(
                f"Failed to get S3 client for {self.organization_schema}: {str(e)}"
            )
            return None

    def _normalize_json_strings(self, data: Union[dict, list, str]) -> Union[dict, list, str]:
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
                return self._normalize_json_strings(
                    parsed
                )  # Recursively normalize if it's a complex JSON
            except json.JSONDecodeError:
                # It's not JSON, return as is
                return data
        else:
            return data

    def copy_email_data(self, upload_data: dict) -> Optional[str]:
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
            s3_client = self._get_s3_client()
            bucket_name = self.data_store.get("storage_bucket")
            if not bucket_name:
                logger.error("storage_bucket not configured in data_store")
                return None
            s3_client.put_object(
                Body=file_content.encode("utf-8"),
                Bucket=bucket_name,
                Key=destination_path,
                ContentType=content_type,
            )
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

    def delete_file(self, s3_url: str) -> bool:
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

            s3_client = self._get_s3_client()
            if s3_client is None:
                return False

            # Check if the object exists before attempting to delete
            try:
                s3_client.head_object(Bucket=bucket_name, Key=key)
            except ClientError as e:
                # If a 404 error is raised, the object does not exist
                if e.response["Error"]["Code"] == "404":
                    logger.warning(f"File not found in S3 bucket: {key}")
                    return True

            # If we've made it here, the object exists - proceed with deletion
            s3_client.delete_object(Bucket=bucket_name, Key=key)
            logger.info(f"File deleted from S3 bucket: {s3_url}")
            return True
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            logger.error(f"S3 Client Error: {error_code} - {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during file delete: {str(e)}")
            return False

    # def download_file(self, s3_url, local_directory):
    #     """
    #     Downloads a file from the specified S3 URL and returns the local path.
    #     """
    #     try:
    #         # Parse the S3 URL to extract bucket name, region, and file path
    #         parsed_url = urlparse(s3_url, allow_fragments=False)
    #         s3_path = parsed_url.path.lstrip("/")
    #         bucket = parsed_url.hostname.split(".")[0]
    #         region = parsed_url.hostname.split(".")[2]
    #         filename = os.path.basename(s3_path)
    #         destination = os.path.join(local_directory, filename)

    #         s3_client = self.get_s3_client(region)
    #         if s3_client is None:
    #             return None
    #         s3_client.download_file(bucket, s3_path, destination)
    #         logger.info(f"Downloaded {s3_url} to {destination}")
    #         return destination
    #     except FileNotFoundError:
    #         logger.error(
    #             f"The file at {s3_url} or directory {local_directory} was not found."
    #         )
    #     except NoCredentialsError:
    #         logger.error("Credentials not available.")
    #         return None
    #     except Exception as e:
    #         logger.error(f"Unexpected error during file download: {str(e)}")
    #         return None

    def generate_presigned_url(self, aws_s3_path: str, expiration: int = 3600) -> Optional[str]:
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

            s3_client = self._get_s3_client(region)
            if s3_client is None:
                return None
            response = s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": s3_file_path},
                ExpiresIn=expiration,
            )
            return response
        except Exception as e:
            logger.error(f"Error generating presigned URL: {str(e)}")
            return None

    def get_bucket_region(self, bucket_name: str) -> Optional[str]:
        """
        Returns the AWS region where the given bucket is hosted.
        Defaults to 'us-east-1' if the region is not specified by AWS.

        Args:
            bucket_name: Name of the bucket

        Returns:
            Optional[str]: AWS region where the bucket is hosted, None if failed
        """
        try:
            s3_client = self._get_s3_client()
            if s3_client is None:
                return None

            # Get the bucket location and rerieve the region
            location = s3_client.get_bucket_location(Bucket=bucket_name)
            region = location["LocationConstraint"]

            # If the region is None, it means the bucket is in us-east-1
            if region is None:
                region = "us-east-1"

            logger.info(f"The bucket '{bucket_name}' is in the region: {region}")
            return region
        except Exception as e:
            logger.error(f"Error determining bucket region: {str(e)}")
            return None

    def upload_data(self, file_content: bytes, file_type: str, destination_path: str) -> Optional[str]:
        """
        Uploads structured or plain text data and returns the S3 URL.

        Args:
            file_content: Content of the file to upload
            file_type: Type of the file to upload
            destination_path: Path to the destination file

        Returns:
            Optional[str]: S3 URL of the uploaded file, None if failed
        """
        try:
            s3_client = self._get_s3_client()
            if s3_client is None:
                return None
            bucket_name = self.data_store.get("storage_bucket")
            storage_region = self.data_store.get("storage_region", "")
            if not bucket_name:
                logger.error("storage_bucket not configured in data_store")
                return None
            s3_client.put_object(
                Body=file_content,
                Bucket=bucket_name,
                Key=destination_path,
                ContentType=file_type,
            )
            s3_url = (
                f"https://{bucket_name}.s3.{storage_region}.amazonaws.com/{destination_path}"
                if storage_region
                else f"https://{bucket_name}.s3.amazonaws.com/{destination_path}"
            )
            logger.info(f"File uploaded to {s3_url}")
            return s3_url
        except NoCredentialsError:
            logger.error("Credentials not available.")
        except Exception as e:
            logger.error(f"Unexpected error during file upload: {str(e)}")
        return None

    def upload_file(self, source_path: str, destination_path: str) -> Optional[str]:
        """
        Uploads a file from the local file system and returns the S3 URL.

        Args:
            source_path: Path to the file to upload
            destination_path: Path to the destination file

        Returns:
            Optional[str]: S3 URL of the uploaded file, None if failed
        """
        try:
            s3_client = self._get_s3_client()
            if s3_client is None:
                return None
            bucket_name = self.data_store.get("storage_bucket")
            storage_region = self.data_store.get("storage_region", "")
            if not bucket_name:
                logger.error("storage_bucket not configured in data_store")
                return None
            s3_client.upload_file(source_path, bucket_name, destination_path)
            s3_url = (
                f"https://{bucket_name}.s3.{storage_region}.amazonaws.com/{destination_path}"
                if storage_region
                else f"https://{bucket_name}.s3.amazonaws.com/{destination_path}"
            )
            logger.info(f"File uploaded to {s3_url}")
            return s3_url
        except FileNotFoundError:
            logger.error(f"The file {source_path} was not found.")
        except NoCredentialsError:
            logger.error("Credentials not available.")
        except Exception as e:
            logger.error(f"Unexpected error during file upload: {str(e)}")
        return None

    def upload_fileobj(self, file_obj, s3_path: str) -> Optional[str]:
        """
        Uploads a file-like object and returns the file's S3 URL.

        Args:
            file_obj: File-like object to upload
            s3_path: Path to the destination file

        Returns:
            Optional[str]: S3 URL of the uploaded file, None if failed
        """
        try:
            s3_client = self._get_s3_client()
            if s3_client is None:
                return None
            bucket_name = self.data_store.get("storage_bucket")
            if not bucket_name:
                logger.error("storage_bucket not configured in data_store")
                return None
            s3_client.upload_fileobj(file_obj, bucket_name, s3_path)
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

    def download_file(
        self, tool_runtime: dict, remote_path: str, local_path: Optional[str] = None
    ) -> str:
        """
        Downloads a file from AWS S3.

        Args:
            tool_runtime: Runtime context containing organization_schema and data_store
            remote_path: S3 URL or path of the file in S3
            local_path: Optional local path to save the downloaded file

        Returns:
            str: JSON string with status_code and message
        """
        # Input validation
        if not tool_runtime or not remote_path or not remote_path.strip():
            return json.dumps(
                {
                    "status_code": 400,
                    "message": "Missing required parameters: tool_runtime and remote_path are required.",
                },
                ensure_ascii=False,
            )

        # Get storage configuration
        data_store = self.data_store
        if not data_store:
            return json.dumps(
                {
                    "status_code": 400,
                    "message": "Missing data_store in tool_runtime.",
                },
                ensure_ascii=False,
            )

        bucket_name = data_store.get("storage_bucket")
        if not bucket_name:
            return json.dumps(
                {
                    "status_code": 400,
                    "message": "storage_bucket not configured in data_store.",
                },
                ensure_ascii=False,
            )

        try:
            s3_client = self._get_s3_client()
            if not s3_client:
                logger.error("Failed to create S3 client")
                return json.dumps(
                    {"status_code": 500, "message": "Failed to create S3 client."},
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
            response = s3_client.get_object(Bucket=bucket_name, Key=s3_path)
            content = response["Body"].read()
            content_type = (
                response.get("ContentType")
                or mimetypes.guess_type(s3_path)[0]
                or "application/octet-stream"
            )

            logger.info(f"File downloaded from S3: s3://{bucket_name}/{s3_path}")

            if local_path:
                local_dir = os.path.dirname(local_path)
                if local_dir:
                    os.makedirs(local_dir, exist_ok=True)
                with open(local_path, "wb") as file:
                    file.write(content)
                logger.info(f"File saved to local path: {local_path}")
                return json.dumps(
                    {
                        "status_code": 200,
                        "message": f"File downloaded and saved to local path: {local_path}.",
                    },
                    ensure_ascii=False,
                )
            else:
                # Return content info when local_path is not provided
                return json.dumps(
                    {
                        "status_code": 200,
                        "message": "File downloaded successfully.",
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
                {"status_code": 401, "message": "No AWS credentials found."},
                ensure_ascii=False,
            )
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            if error_code == "NoSuchKey":
                bucket_info = (
                    f"s3://{bucket_name}/{s3_path}"
                    if "bucket_name" in locals() and "s3_path" in locals()
                    else remote_path
                )
                logger.error(f"File not found: {bucket_info}")
                return json.dumps(
                    {
                        "status_code": 404,
                        "message": f"File not found: {bucket_info}.",
                    },
                    ensure_ascii=False,
                )
            else:
                logger.error(f"AWS S3 error in download_file: {str(e)}")
                return json.dumps(
                    {
                        "status_code": 500,
                        "message": f"Failed to download file: {str(e)}",
                    },
                    ensure_ascii=False,
                )
        except Exception as e:
            logger.error(f"Unexpected error in download_file: {str(e)}")
            return json.dumps(
                {
                    "status_code": 500,
                    "message": f"Failed to download file from S3: {str(e)}",
                },
                ensure_ascii=False,
            )

    def tool_upload_file(
        self, tool_runtime: dict, source_path: str, file_name: str
    ) -> str:
        """
        Tool wrapper for uploading a file to S3.
        Uploads a local file to AWS S3.

        Args:
            tool_runtime: Runtime context containing organization_schema and data_store
            source_path: Local path of the file to upload
            file_name: Name of the file in the S3 bucket

        Returns:
            str: JSON string with status_code and message
        """
        # Input validation
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
                    "message": "Missing required parameters: tool_runtime, source_path, and file_name are required.",
                },
                ensure_ascii=False,
            )

        # Get storage configuration
        data_store = self.data_store
        if not data_store:
            return json.dumps(
                {
                    "status_code": 400,
                    "message": "Missing data_store in tool_runtime.",
                },
                ensure_ascii=False,
            )

        bucket_name = data_store.get("storage_bucket")
        if not bucket_name:
            return json.dumps(
                {
                    "status_code": 400,
                    "message": "storage_bucket not configured in data_store.",
                },
                ensure_ascii=False,
            )

        try:
            # Prepare file path: remove extension, clean dots, preserve source extension
            base_name = file_name.rsplit(".", 1)[0].replace(".", "")
            # Extract extension from source_path, default to empty if no extension
            source_ext = source_path.rsplit(".", 1)[-1] if "." in source_path else ""
            file_extension = f".{source_ext}" if source_ext else ""
            file_name_with_extension = f"{base_name}{file_extension}"

            # Construct destination path
            data_folder = data_store.get("storage_folder", "").rstrip("/")
            destination_path = (
                f"{data_folder}/{file_name_with_extension}"
                if data_folder
                else file_name_with_extension
            )

            # Upload to S3
            result = self.upload_file(
                source_path=source_path, destination_path=destination_path
            )

            if result:
                logger.info(f"File uploaded successfully: {result}")
                return json.dumps(
                    {
                        "status_code": 200,
                        "message": f"File uploaded successfully: {result}.",
                    },
                    ensure_ascii=False,
                )

            logger.error("Failed to upload file: AWS S3 returned None")
            return json.dumps(
                {"status_code": 500, "message": "Failed to upload file."},
                ensure_ascii=False,
            )

        except FileNotFoundError:
            logger.error(f"File not found: {source_path}")
            return json.dumps(
                {"status_code": 404, "message": f"File not found: {source_path}."},
                ensure_ascii=False,
            )
        except requests.HTTPError as e:
            status_code = e.response.status_code if e.response else 500
            logger.error(f"HTTP error uploading file: {e}")
            return json.dumps(
                {
                    "status_code": status_code,
                    "message": f"HTTP error uploading file: {status_code}.",
                },
                ensure_ascii=False,
            )
        except NoCredentialsError:
            logger.error("No AWS credentials found.")
            return json.dumps(
                {"status_code": 401, "message": "No AWS credentials found."},
                ensure_ascii=False,
            )
        except Exception as e:
            logger.error(f"Failed to upload file: {str(e)}")
            return json.dumps(
                {
                    "status_code": 500,
                    "message": f"Failed to upload file: {str(e)}",
                },
                ensure_ascii=False,
            )

    def tool_upload_structured_data(
        self, tool_runtime: dict, data: Union[Dict, List[Dict]], file_name: str
    ) -> str:
        """
        Tool wrapper for uploading structured data (JSON) to S3.
        Uploads structured data (dict or list of dicts) to AWS S3 as JSON files.

        Args:
            tool_runtime: Runtime context containing organization_schema and data_store
            data: Structured data to upload (dict or list of dicts)
            file_name: Name of the file to create

        Returns:
            str: JSON string with status_code and message
        """
        # Input validation
        if not tool_runtime or not data or not file_name or not file_name.strip():
            return json.dumps(
                {
                    "status_code": 400,
                    "message": "Missing required parameters: tool_runtime, data, and file_name are required.",
                },
                ensure_ascii=False,
            )

        # Validate data structure
        if isinstance(data, list) and not all(isinstance(item, dict) for item in data):
            return json.dumps(
                {
                    "status_code": 400,
                    "message": "data list must contain only dictionaries.",
                },
                ensure_ascii=False,
            )

        # Get storage configuration
        data_store = self.data_store
        if not data_store:
            return json.dumps(
                {
                    "status_code": 400,
                    "message": "Missing data_store in tool_runtime.",
                },
                ensure_ascii=False,
            )

        bucket_name = data_store.get("storage_bucket")
        if not bucket_name:
            return json.dumps(
                {
                    "status_code": 400,
                    "message": "storage_bucket not configured in data_store.",
                },
                ensure_ascii=False,
            )

        try:
            # Normalize and serialize data
            processed_data = self._normalize_json_strings(data)
            file_content = json.dumps(processed_data, ensure_ascii=False).encode(
                "utf-8"
            )

            # Prepare file path: remove extension, clean dots, add .json
            base_name = file_name.rsplit(".", 1)[0].replace(".", "")
            file_name_with_extension = f"{base_name}.json"

            # Construct destination path
            data_folder = data_store.get("storage_folder", "").rstrip("/")
            destination_path = (
                f"{data_folder}/{file_name_with_extension}"
                if data_folder
                else file_name_with_extension
            )

            # Upload to S3
            result = self.upload_data(
                file_content=file_content,
                file_type="application/json",
                destination_path=destination_path,
            )

            if result:
                logger.info(f"Structured data uploaded successfully: {result}")
                return json.dumps(
                    {
                        "status_code": 200,
                        "message": f"Structured data uploaded successfully: {result}.",
                    },
                    ensure_ascii=False,
                )

            logger.error("Failed to upload structured data: AWS S3 returned None")
            return json.dumps(
                {"status_code": 500, "message": "Failed to upload structured data."},
                ensure_ascii=False,
            )

        except requests.HTTPError as e:
            status_code = e.response.status_code if e.response else 500
            logger.error(f"HTTP error uploading structured data: {e}")
            return json.dumps(
                {
                    "status_code": status_code,
                    "message": f"HTTP error uploading structured data: {status_code}.",
                },
                ensure_ascii=False,
            )
        except NoCredentialsError:
            logger.error("No AWS credentials found.")
            return json.dumps(
                {"status_code": 401, "message": "No AWS credentials found."},
                ensure_ascii=False,
            )
        except Exception as e:
            logger.error(f"Failed to upload structured data: {str(e)}")
            return json.dumps(
                {
                    "status_code": 500,
                    "message": f"Failed to upload structured data: {str(e)}",
                },
                ensure_ascii=False,
            )

    def tool_upload_text_data(
        self, tool_runtime: dict, data: str, file_name: str
    ) -> str:
        """
        Tool wrapper for uploading text data to S3.
        Uploads plain text data to AWS S3 as text files.

        Args:
            tool_runtime: Runtime context containing organization_schema and data_store
            data: Text data to upload
            file_name: Name of the file to create

        Returns:
            str: JSON string with status_code and message
        """
        # Input validation
        if not tool_runtime or not data or not file_name or not file_name.strip():
            return json.dumps(
                {
                    "status_code": 400,
                    "message": "Missing required parameters: tool_runtime, data, and file_name are required.",
                },
                ensure_ascii=False,
            )

        # Get storage configuration
        data_store = self.data_store
        if not data_store:
            return json.dumps(
                {
                    "status_code": 400,
                    "message": "Missing data_store in tool_runtime.",
                },
                ensure_ascii=False,
            )

        bucket_name = data_store.get("storage_bucket")
        if not bucket_name:
            return json.dumps(
                {
                    "status_code": 400,
                    "message": "storage_bucket not configured in data_store.",
                },
                ensure_ascii=False,
            )

        try:
            # Prepare file content
            file_content = str(data).encode("utf-8")

            # Prepare file path: remove extension, clean dots, add .txt
            base_name = file_name.rsplit(".", 1)[0].replace(".", "")
            file_name_with_extension = f"{base_name}.txt"

            # Construct destination path
            data_folder = data_store.get("storage_folder", "").rstrip("/")
            destination_path = (
                f"{data_folder}/{file_name_with_extension}"
                if data_folder
                else file_name_with_extension
            )

            # Upload to S3
            result = self.upload_data(
                file_content=file_content,
                file_type="text/plain",
                destination_path=destination_path,
            )

            if result:
                logger.info(f"Text data uploaded successfully: {result}")
                return json.dumps(
                    {
                        "status_code": 200,
                        "message": f"Text data uploaded successfully: {result}.",
                    },
                    ensure_ascii=False,
                )

            logger.error("Failed to upload text data: AWS S3 returned None")
            return json.dumps(
                {"status_code": 500, "message": "Failed to upload text data."},
                ensure_ascii=False,
            )

        except requests.HTTPError as e:
            status_code = e.response.status_code if e.response else 500
            logger.error(f"HTTP error uploading text data: {e}")
            return json.dumps(
                {
                    "status_code": status_code,
                    "message": f"HTTP error uploading text data: {status_code}.",
                },
                ensure_ascii=False,
            )
        except NoCredentialsError:
            logger.error("No AWS credentials found.")
            return json.dumps(
                {"status_code": 401, "message": "No AWS credentials found."},
                ensure_ascii=False,
            )
        except Exception as e:
            logger.error(f"Failed to upload text data: {str(e)}")
            return json.dumps(
                {
                    "status_code": 500,
                    "message": f"Failed to upload text data: {str(e)}",
                },
                ensure_ascii=False,
            )


class AWSS3Validator:
    @staticmethod
    def validate_credentials(credentials: Dict) -> Tuple[bool, Optional[str]]:
        """
        Validates S3 Bucket credentials by attempting to list buckets.
        Returns a tuple of (is_valid, error_message).
        """
        # Check if all required fields are present
        required_fields = ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"]
        for field in required_fields:
            if field not in credentials:
                return False, f"Missing required field: {field}"
        try:
            # Initialize boto3 S3 client with provided credentials
            client_kwargs = {
                "aws_access_key_id": credentials["AWS_ACCESS_KEY_ID"],
                "aws_secret_access_key": credentials["AWS_SECRET_ACCESS_KEY"],
                "config": Config(signature_version="s3v4"),
            }
            s3_client = boto3.client("s3", **client_kwargs)

            # Attempt to list buckets as a credentials test
            s3_client.list_buckets()
            return True, None

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_message = e.response.get("Error", {}).get("Message", str(e))
            return False, f"S3 Bucket validation failed: {error_code} {error_message}"

            # if error_code == "InvalidAccessKeyId":
            #     return False, "Invalid Access Key ID provided"
            # elif error_code == "SignatureDoesNotMatch":
            #     return False, "Invalid Secret Access Key provided"
            # elif error_code == "AccessDenied":
            #     return (
            #         False,
            #         "Access denied: IAM user does not have sufficient permissions",
            #     )
            # else:
            #     return False, f"S3 Bucket validation failed: {error_message}"

        except NoCredentialsError:
            return False, "No credentials provided or credentials are invalid"

        except Exception as e:
            return False, f"Error validating S3 Bucket credentials: {str(e)}"
