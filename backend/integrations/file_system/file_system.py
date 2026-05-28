# Custom libraries
from logger import configure_logging

# Default libraries
from typing import List, Optional, Union
import csv
import io
import json
import mimetypes
import os

# Installed libraries
from dotenv import load_dotenv
import shutil


load_dotenv()

logger = configure_logging(__name__)


class FileSystem:
    """
    Handles operations for interacting with a mounted file system.
    """

    def __init__(self, data_store=None):
        """
        Initializes FileSystem with data store configurations.

        Args:
            data_store: Data store configurations
        """
        self.data_store = data_store or {}
        self._container_mount = self._get_container_mount()

    def _get_container_mount(self) -> Optional[str]:
        """
        Determines the container mount based on the 'STORAGE_MOUNT_POINTS' and data store.

        Returns:
            Optional[str]: Container mount path, None if not found
        """
        try:
            environment_storage_mounts = os.getenv("STORAGE_MOUNT_POINTS")
            if environment_storage_mounts:
                mounts = json.loads(environment_storage_mounts)

                # Handle double-encoded JSON
                if isinstance(mounts, str):
                    mounts = json.loads(mounts)

                for mount in mounts:
                    if mount.get("host") == self.data_store.get("storage_bucket"):
                        if mount.get("container") and os.path.isdir(
                            mount.get("container")
                        ):
                            return mount.get("container")
            return None
        except Exception as e:
            logger.error(f"Failed to get container mount: {str(e)}")
            return None

    def _generate_csv_content(self, data: Union[dict, List[dict]]) -> str:
        """
        Generate CSV content from structured data (dict or list of dicts).
        
        Args:
            data: Structured data to generate CSV content from

        Returns:
            str: CSV content
        """
        output = io.StringIO()

        if isinstance(data, dict):
            # Single dictionary -> single row
            writer = csv.DictWriter(output, fieldnames=data.keys())
            writer.writeheader()
            writer.writerow(data)

        elif isinstance(data, list) and data:
            # List of dictionaries -> multiple rows
            # Get all unique keys from all dictionaries
            all_keys = set()
            for item in data:
                if isinstance(item, dict):
                    all_keys.update(item.keys())

            fieldnames = sorted(all_keys)  # Sort for consistent column order
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writeheader()

            for item in data:
                if isinstance(item, dict):
                    writer.writerow(item)

        else:
            # Empty data
            writer = csv.writer(output)
            writer.writerow([])  # Empty row

        return output.getvalue()

    def _is_json(self, data: str) -> bool:
        """
        Check if a string is valid JSON.

        Args:
            data: Data to check if it is valid JSON

        Returns:
            bool: True if data is valid JSON, False otherwise
        """
        try:
            json.loads(data)
            return True
        except json.JSONDecodeError:
            return False

    def _normalize_json_strings(self, data: Union[dict, list, str]) -> Union[dict, list, str]:
        """
        Recursively process all string values in the given data.
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
        Uploads the email data to the mounted storage and returns the mounted path.

        Args:
            upload_data: Email data to upload

        Returns:
            str: Mounted path to the uploaded email data, None if failed
        """
        processed_data = self._normalize_json_strings(upload_data)
        file_content = json.dumps(processed_data, ensure_ascii=False, default=str)
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
            if self._container_mount:
                destination = os.path.join(
                    self._container_mount, destination_path.lstrip("/")
                )
                dest_dir = os.path.dirname(destination)
                if dest_dir:
                    os.makedirs(dest_dir, exist_ok=True)
                with open(destination, "w", encoding="utf-8") as file:
                    file.write(file_content)
                logger.info(f"Data saved to {destination}")
                return destination
            else:
                logger.error("Mounted storage is not available.")
                return None
        except Exception as e:
            logger.error(f"Failed to upload data: {str(e)}")
            return None

    def create_file(self, upload_data: Union[dict, list, str], file_name: str) -> Optional[str]:
        """
        Creates a file and writes data to it in the mounted storage.

        Args:
            upload_data: Data to write to the file
            file_name: Name of the file to create

        Returns:
            str: Full path to the created file on success, None on failure
        """
        try:
            if not self._container_mount:
                logger.error("Mounted storage is not available")
                return None

            # Determine content type and extension
            if isinstance(upload_data, dict) or (
                isinstance(upload_data, str) and self._is_json(upload_data)
            ):
                if isinstance(upload_data, str):
                    upload_data = json.loads(upload_data)
                processed_data = self._normalize_json_strings(upload_data)
                file_content = json.dumps(processed_data, ensure_ascii=False)
                file_extension = ".json"
            elif isinstance(upload_data, list) and all(
                isinstance(item, dict) for item in upload_data
            ):
                processed_data = self._normalize_json_strings(upload_data)
                file_content = json.dumps(processed_data, ensure_ascii=False)
                file_extension = ".json"
            else:
                file_content = str(upload_data)
                file_extension = ".txt"

            # Prepare file name
            base_name = file_name.rsplit(".", 1)[0]
            base_name = base_name.replace(".", "")
            file_name_with_extension = f"{base_name}{file_extension}"

            data_folder = self.data_store.get("storage_folder", None)
            file_path = (
                f"{data_folder.rstrip('/')}/{file_name_with_extension}"
                if data_folder
                else file_name_with_extension
            )

            destination = os.path.join(self._container_mount, file_path.lstrip("/"))
            dest_dir = os.path.dirname(destination)
            if dest_dir:
                os.makedirs(dest_dir, exist_ok=True)

            with open(destination, "w", encoding="utf-8") as file:
                file.write(file_content)

            logger.info(f"File written successfully: {destination}")
            return destination

        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error in write_file: {str(e)}")
            return None
        except OSError as e:
            logger.error(f"File system error in write_file: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in write_file: {str(e)}")
            return None

    def delete_file(self, mounted_path: str) -> bool:
        """
        Deletes a file from the specified mounted storage path.

        Args:
            mounted_path: Path to the file to delete

        Returns:
            bool: True if file was deleted successfully, False otherwise
        """
        try:
            if self._container_mount:
                file_path = os.path.join(self._container_mount, mounted_path)
                if os.path.exists(file_path):
                    os.remove(file_path)
                    logger.info(f"File deleted from mounted path: {file_path}")
                    return True
                else:
                    logger.info(f"File not found at mounted path: {file_path}")
                    return True
            else:
                logger.error("Mounted storage is not available.")
                return False
        except Exception as e:
            logger.error(f"Unexpected error during file delete: {str(e)}")
            return False

    def download_file(self, mounted_path, local_directory):
        """
        Downloads a file from the specified mounted storage path and returns the local path.
        """
        try:
            source = mounted_path
            filename = os.path.basename(source)
            destination = os.path.join(local_directory, filename)
            shutil.copy(source, destination)
            logger.info(f"Copied {source} to {destination}")
            return destination
        except FileNotFoundError:
            logger.error(
                f"The file at {mounted_path} or directory {local_directory} was not found."
            )
            return None
        except Exception as e:
            logger.error(f"Unexpected error during file download: {str(e)}")
            return None

    def upload_file(self, source_path: str, destination_path: str) -> Optional[str]:
        """
        Uploads a file from the local file system and returns the mounted path.

        Args:
            source_path: Path to the file to upload
            destination_path: Path to the destination file

        Returns:
            str: Mounted path to the uploaded file, None if failed
        """
        try:
            if self._container_mount:
                destination = os.path.join(
                    self._container_mount, destination_path.lstrip("/")
                )
                dest_dir = os.path.dirname(destination)
                if dest_dir:
                    os.makedirs(dest_dir, exist_ok=True)
                shutil.copy(source_path, destination)
                logger.info(f"File saved to mounted path {destination}")
                return destination
            else:
                logger.error("Mounted storage is not available.")
                return None
        except FileNotFoundError:
            logger.error(f"The file {source_path} was not found.")
            return None
        except Exception as e:
            logger.error(f"Unexpected error during file upload: {str(e)}")
            return None

    def upload_fileobj(self, file_obj, mounted_path: str) -> Optional[str]:
        """
        Uploads a file-like object and returns the file's mounted path.

        Args:
            file_obj: File-like object to upload
            mounted_path: Path to the destination file

        Returns:
            str: Full path to the uploaded file on success, None on failure
        """
        try:
            if self._container_mount:
                destination_path = os.path.join(
                    self._container_mount, mounted_path.lstrip("/")
                )
                dest_dir = os.path.dirname(destination_path)
                if dest_dir:
                    os.makedirs(dest_dir, exist_ok=True)
                with open(destination_path, "wb") as destination_file:
                    shutil.copyfileobj(file_obj, destination_file)
                logger.info(f"File object saved to mounted path: {destination_path}")
                return destination_path
            else:
                logger.error("Mounted storage is not available.")
                return None
        except FileNotFoundError:
            logger.error(
                "The file object could not be uploaded because it was not found."
            )
            return None
        except Exception as e:
            logger.error(f"Unexpected error during file upload: {str(e)}")
            return None

    def copy_file(
        self, tool_runtime: dict, source_path: str, destination_path: str
    ) -> str:
        """
        Copies a file within the mounted storage.

        Args:
            tool_runtime: Runtime context containing data_store
            source_path: Source file path
            destination_path: Destination file path

        Returns:
            str: JSON string with status_code and message
        """
        # Input validation
        if (
            not tool_runtime
            or not source_path
            or not destination_path
            or not source_path.strip()
            or not destination_path.strip()
        ):
            return json.dumps(
                {
                    "status_code": 400,
                    "message": "Missing required parameters: tool_runtime, source_path and destination_path are required.",
                },
                ensure_ascii=False,
            )

        try:
            if not self._container_mount:
                return json.dumps(
                    {"status_code": 500, "message": "Mounted storage is not available."},
                    ensure_ascii=False,
                )

            src = os.path.join(self._container_mount, source_path.lstrip("/"))
            dest = os.path.join(self._container_mount, destination_path.lstrip("/"))

            if not os.path.isfile(src):
                logger.error(f"Source file not found: {src}")
                return json.dumps(
                    {"status_code": 404, "message": f"Source file not found: {src}."},
                    ensure_ascii=False,
                )

            dest_dir = os.path.dirname(dest)
            if dest_dir:
                os.makedirs(dest_dir, exist_ok=True)
            shutil.copy2(src, dest)

            logger.info(f"File copied successfully: {src} -> {dest}")
            return json.dumps(
                {
                    "status_code": 200,
                    "message": f"File from {src} copied successfully: {dest}.",
                },
                ensure_ascii=False,
            )

        except OSError as e:
            logger.error(f"File system error in copy_file: {str(e)}")
            return json.dumps(
                {
                    "status_code": 500,
                    "message": f"Failed to copy file: {str(e)}",
                },
                ensure_ascii=False,
            )
        except Exception as e:
            logger.error(f"Unexpected error in copy_file: {str(e)}")
            return json.dumps(
                {
                    "status_code": 500,
                    "message": f"Failed to copy file: {str(e)}",
                },
                ensure_ascii=False,
            )

    def list_directory(self, tool_runtime: dict, directory_path: str = "/") -> str:
        """
        Lists contents of a directory in the mounted storage.

        Args:
            tool_runtime: Runtime context containing data_store
            directory_path: Directory path to list (default: "/")

        Returns:
            str: JSON string with status_code and message
        """
        # Input validation
        if not tool_runtime:
            return json.dumps(
                {
                    "status_code": 400,
                    "message": "tool_runtime is required.",
                },
                ensure_ascii=False,
            )

        if not directory_path:
            directory_path = "/"  # Default to root
        elif not directory_path.strip():
            return json.dumps(
                {"status_code": 400, "message": "directory_path cannot be empty."},
                ensure_ascii=False,
            )

        try:
            if not self._container_mount:
                return json.dumps(
                    {"status_code": 500, "message": "Mounted storage is not available."},
                    ensure_ascii=False,
                )

            target_dir = os.path.join(self._container_mount, directory_path.lstrip("/"))

            if not os.path.isdir(target_dir):
                logger.error(f"Path is not a directory: {target_dir}")
                return json.dumps(
                    {
                        "status_code": 400,
                        "message": f"Path is not a directory: {target_dir}.",
                    },
                    ensure_ascii=False,
                )

            contents = os.listdir(target_dir)
            logger.info(
                f"Directory listed successfully: {target_dir} ({len(contents)} items)"
            )
            return json.dumps(
                {
                    "status_code": 200,
                    "message": f"Directory contents: {contents}.",
                },
                ensure_ascii=False,
            )

        except OSError as e:
            logger.error(f"File system error in list_directory: {str(e)}")
            return json.dumps(
                {
                    "status_code": 500,
                    "message": f"Failed to list directory: {str(e)}",
                },
                ensure_ascii=False,
            )
        except Exception as e:
            logger.error(f"Unexpected error in list_directory: {str(e)}")
            return json.dumps(
                {
                    "status_code": 500,
                    "message": f"Failed to list directory: {str(e)}",
                },
                ensure_ascii=False,
            )

    def move_file(
        self, tool_runtime: dict, source_path: str, destination_path: str
    ) -> str:
        """
        Moves a file within the mounted storage.

        Args:
            tool_runtime: Runtime context containing data_store
            source_path: Source file path
            destination_path: Destination file path

        Returns:
            str: JSON string with status_code and message
        """
        # Input validation
        if not tool_runtime or not source_path or not destination_path:
            return json.dumps(
                {
                    "status_code": 400,
                    "message": "Missing required parameters: source_path and destination_path are required.",
                },
                ensure_ascii=False,
            )

        if not source_path.strip() or not destination_path.strip():
            return json.dumps(
                {
                    "status_code": 400,
                    "message": "source_path and destination_path cannot be empty.",
                },
                ensure_ascii=False,
            )

        try:
            if not self._container_mount:
                return json.dumps(
                    {"status_code": 500, "message": "Mounted storage is not available."},
                    ensure_ascii=False,
                )

            src = os.path.join(self._container_mount, source_path.lstrip("/"))
            dest = os.path.join(self._container_mount, destination_path.lstrip("/"))

            if not os.path.isfile(src):
                logger.error(f"Source file not found: {src}")
                return json.dumps(
                    {"status_code": 404, "message": f"Source file not found: {src}."},
                    ensure_ascii=False,
                )

            dest_dir = os.path.dirname(dest)
            if dest_dir:
                os.makedirs(dest_dir, exist_ok=True)
            os.rename(src, dest)

            logger.info(f"File moved successfully: {src} -> {dest}")
            return json.dumps(
                {
                    "status_code": 200,
                    "message": f"File from {src} moved successfully: {dest}.",
                },
                ensure_ascii=False,
            )

        except OSError as e:
            logger.error(f"File system error in move_file: {str(e)}")
            return json.dumps(
                {
                    "status_code": 500,
                    "message": f"Failed to move file: {str(e)}",
                },
                ensure_ascii=False,
            )
        except Exception as e:
            logger.error(f"Unexpected error in move_file: {str(e)}")
            return json.dumps(
                {
                    "status_code": 500,
                    "message": f"Failed to move file: {str(e)}",
                },
                ensure_ascii=False,
            )

    def read_file(
        self, tool_runtime: dict, remote_path: str, local_path: Optional[str] = None
    ) -> str:
        """
        Reads a file from the mounted storage.

        Args:
            tool_runtime: Runtime context containing data_store
            remote_path: Path to the file to read
            local_path: Optional local path to save the file

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

        try:
            if not self._container_mount:
                return json.dumps(
                    {"status_code": 500, "message": "Mounted storage is not available."},
                    ensure_ascii=False,
                )

            full_path = (
                os.path.join(self._container_mount, remote_path.lstrip("/"))
                if not remote_path.startswith(self._container_mount)
                else remote_path
            )

            if not os.path.isfile(full_path):
                logger.error(f"File not found: {full_path}")
                return json.dumps(
                    {"status_code": 404, "message": f"File not found: {full_path}."},
                    ensure_ascii=False,
                )

            with open(full_path, "rb") as file:
                content = file.read()

            content_type = (
                mimetypes.guess_type(full_path)[0] or "application/octet-stream"
            )
            logger.info(f"File read successfully from: {full_path}")

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
                        "message": f"File read and saved to local path: {local_path}.",
                    },
                    ensure_ascii=False,
                )
            else:
                # Return content info when local_path is not provided
                return json.dumps(
                    {
                        "status_code": 200,
                        "message": "File read successfully.",
                        "data": {
                            "content_length": len(content),
                            "content_type": content_type,
                        },
                    },
                    ensure_ascii=False,
                )

        except OSError as e:
            logger.error(f"File system error in read_file: {str(e)}")
            return json.dumps(
                {
                    "status_code": 500,
                    "message": f"Failed to read file: {str(e)}",
                },
                ensure_ascii=False,
            )
        except Exception as e:
            logger.error(f"Unexpected error in read_file: {str(e)}")
            return json.dumps(
                {
                    "status_code": 500,
                    "message": f"Failed to read file: {str(e)}",
                },
                ensure_ascii=False,
            )

    def search_file(
        self, tool_runtime: dict, keyword: str, search_path: str = "/"
    ) -> str:
        """
        Searches for files containing the keyword in their names.

        Args:
            tool_runtime: Runtime context containing data_store
            keyword: Keyword to search for in filenames
            search_path: Directory to search in (default: "/")

        Returns:
            str: JSON string with status_code and message
        """
        # Input validation
        if not tool_runtime or not keyword or not keyword.strip():
            return json.dumps(
                {
                    "status_code": 400,
                    "message": "keyword is required and cannot be empty.",
                },
                ensure_ascii=False,
            )

        if not search_path or not search_path.strip():
            search_path = "/"  # Default to root

        try:
            if not self._container_mount:
                return json.dumps(
                    {"status_code": 500, "message": "Mounted storage is not available."},
                    ensure_ascii=False,
                )

            result = []
            base_path = os.path.join(self._container_mount, search_path.lstrip("/"))

            if not os.path.isdir(base_path):
                logger.error(f"Search path is not a directory: {base_path}")
                return json.dumps(
                    {
                        "status_code": 400,
                        "message": f"Search path is not a directory: {base_path}.",
                    },
                    ensure_ascii=False,
                )

            for root, _, files in os.walk(base_path):
                for file in files:
                    if keyword.lower() in file.lower():
                        result.append(os.path.join(root, file))

            logger.info(
                f"File search completed: found {len(result)} file(s) matching '{keyword}' in {search_path}."
            )
            return json.dumps(
                {
                    "status_code": 200,
                    "message": f"Found {len(result)} file(s) matching '{keyword}': {result}.",
                },
                ensure_ascii=False,
            )

        except OSError as e:
            logger.error(f"File system error in file_search: {str(e)}")
            return json.dumps(
                {
                    "status_code": 500,
                    "message": f"File search failed: {str(e)}",
                },
                ensure_ascii=False,
            )
        except Exception as e:
            logger.error(f"Unexpected error in file_search: {str(e)}")
            return json.dumps(
                {
                    "status_code": 500,
                    "message": f"File search failed: {str(e)}",
                },
                ensure_ascii=False,
            )

    def tool_create_structured_file(
        self,
        tool_runtime: dict,
        data: Union[dict, List[dict]],
        file_name: str,
        format: str = "json",
    ) -> str:
        """
        Tool wrapper for creating structured data files.
        Creates a structured data file in JSON or CSV format.

        Args:
            tool_runtime: Runtime context containing data_store
            data: Structured data as dictionary or list of dictionaries
            file_name: Name of the file to create
            format: Output format - "json" or "csv". Defaults to "json"

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

        if isinstance(data, list) and not all(isinstance(item, dict) for item in data):
            return json.dumps(
                {
                    "status_code": 400,
                    "message": "data list must contain only dictionaries.",
                },
                ensure_ascii=False,
            )

        if format not in ["json", "csv"]:
            return json.dumps(
                {"status_code": 400, "message": "format must be 'json' or 'csv'."},
                ensure_ascii=False,
            )

        try:
            # Generate file content based on format
            if format == "json":
                processed_data = self._normalize_json_strings(data)
                file_content = json.dumps(processed_data, indent=2, ensure_ascii=False)
                file_extension = "json"
            else:  # csv
                file_content = self._generate_csv_content(data)
                file_extension = "csv"

            # Prepare file name
            base_name = file_name.rsplit(".", 1)[0].replace(".", "")
            structured_file_name = f"{base_name}.{file_extension}"

            # Create file using existing method
            result = self.create_file(file_content, structured_file_name)   

            if result:
                logger.info(f"Structured file created successfully: {result}")
                return json.dumps(
                    {
                        "status_code": 200,
                        "message": f"Structured file created successfully: {result}.",
                    },
                    ensure_ascii=False,
                )

            logger.error("Failed to create structured file: filesystem returned None")
            return json.dumps(
                {"status_code": 500, "message": "Failed to create structured file."},
                ensure_ascii=False,
            )

        except Exception as e:
            logger.error(f"Failed to create structured file: {str(e)}")
            return json.dumps(
                {
                    "status_code": 500,
                    "message": f"Failed to create structured file: {str(e)}",
                },
                ensure_ascii=False,
            )

    def tool_create_text_file(
        self, tool_runtime: dict, content: str, file_name: str
    ) -> str:
        """
        Tool wrapper for creating text files.
        Creates a plain text file from string content.

        Args:
            tool_runtime: Runtime context containing data_store
            content: Text content to write to the file
            file_name: Name of the file to create

        Returns:
            str: JSON string with status_code and message
        """
        # Input validation
        if not tool_runtime or not content or not file_name or not file_name.strip():
            return json.dumps(
                {
                    "status_code": 400,
                    "message": "Missing required parameters: tool_runtime, content, and file_name are required.",
                },
                ensure_ascii=False,
            )

        try:
            # Prepare file name with .txt extension
            base_name = file_name.rsplit(".", 1)[0].replace(".", "")
            txt_file_name = f"{base_name}.txt"

            # Create file using existing method
            result = self.create_file(content, txt_file_name)

            if result:
                logger.info(f"Text file created successfully: {result}")
                return json.dumps(
                    {
                        "status_code": 200,
                        "message": f"Text file created successfully: {result}.",
                    },
                    ensure_ascii=False,
                )

            logger.error("Failed to create text file: filesystem returned None")
            return json.dumps(
                {"status_code": 500, "message": "Failed to create text file."},
                ensure_ascii=False,
            )

        except Exception as e:
            logger.error(f"Failed to create text file: {str(e)}")
            return json.dumps(
                {
                    "status_code": 500,
                    "message": f"Failed to create text file: {str(e)}",
                },
                ensure_ascii=False,
            )

    def tool_delete_file(self, tool_runtime: dict, file_path: str) -> str:
        """
        Deletes a file from the mounted storage path.

        Args:
            tool_runtime: Runtime context containing data_store
            file_path: Path of the file to delete

        Returns:
            str: JSON string with status_code and message
        """
        # Input validation
        if not tool_runtime or not file_path or not file_path.strip():
            return json.dumps(
                {
                    "status_code": 400,
                    "message": "Missing required parameters: tool_runtime and file_path are required.",
                },
                ensure_ascii=False,
            )

        try:
            # Check if file exists before deletion for better error reporting
            if not self._container_mount:
                return json.dumps(
                    {"status_code": 500, "message": "Mounted storage is not available."},
                    ensure_ascii=False,
                )

            full_path = os.path.join(self._container_mount, file_path.lstrip("/"))

            if not os.path.isfile(full_path):
                logger.error(f"File not found for deletion: {full_path}")
                return json.dumps(
                    {
                        "status_code": 404,
                        "message": f"File not found: {full_path}.",
                    },
                    ensure_ascii=False,
                )

            # Use delete_file function
            result = self.delete_file(file_path)

            if result:
                logger.info(f"File deleted successfully: {full_path}")
                return json.dumps(
                    {
                        "status_code": 200,
                        "message": f"File deleted successfully: {full_path}.",
                    },
                    ensure_ascii=False,
                )
            else:
                return json.dumps(
                    {
                        "status_code": 500,
                        "message": "Failed to delete file.",
                    },
                    ensure_ascii=False,
                )

        except Exception as e:
            logger.error(f"Unexpected error in tool_delete_file: {str(e)}")
            return json.dumps(
                {
                    "status_code": 500,
                    "message": f"Failed to delete file: {str(e)}",
                },
                ensure_ascii=False,
            )
