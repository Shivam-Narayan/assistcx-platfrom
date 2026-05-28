# Custom libraries
from logger import configure_logging
from integrations.aws.aws_s3 import AWSS3
from integrations.minio_storage.client import MinIOStorage
from integrations.file_system.file_system import FileSystem
# SharePoint not in use; re-enable when needed.
# from integrations.office_365.sharepoint import Sharepoint
from schemas.data_file_schema import DataFileDetail

# Database modules
from repository.data_file_repository import DataFileRepository
from repository.data_collection_repository import DataCollectionRepository
from sqlalchemy.orm import Session

# Default libraries
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID
import os
import requests

# Installed libraries
from celery_worker import celery
from dotenv import load_dotenv
from fastapi import HTTPException


logger = configure_logging(__name__)

load_dotenv()


class DocumentFile:
    """A class for processing data files."""

    def __init__(self, organization_schema: str, db: Optional[Session] = None):
        self.db = db
        self.organization_schema = organization_schema
        self.data_collection_repository = DataCollectionRepository(self.db)
        self.data_file_repository = DataFileRepository(self.db)
        self.allowed_extensions = ["pdf", "md", "docx", "pptx"]
        self.file_upload_limit = 10
        self.max_file_size = 52428800

    def upload_data_files(
        self, data_files: List, source: str, data_collection_id: UUID
    ) -> Optional[Dict[str, Any]]:
        """
        Uploads data files to the specified data collection.

        Args:
            data_files (List): List of data files to be uploaded.
            source (str): Source of the data files (e.g., "local").
            data_collection_id (UUID): UUID of the data collection where files will be uploaded.

        Returns:
            Dict[str, Any]: Result of uploaded data files, with the following structure:
                - upload_successes (List): Successfully uploaded files with metadata.
                - upload_failures (List): Failed uploads with corresponding error messages.
        """
        try:
            if len(data_files) > self.file_upload_limit:
                raise HTTPException(
                    status_code=400,
                    detail=f"You can only upload a maximum of {self.file_upload_limit} files at a time.",
                )

            upload_successes = []
            upload_failures = []

            # Get the current organization schema and fetch preferences
            # org_preferences = (
            #     environment.get_preferences(self.organization_schema) or {}
            # )

            # Set default data store preferences if not provided in the organization preferences
            # data_store = org_preferences.get(
            #     "data_store",
            #     {
            #         "storage_type": "local",
            #         "storage_bucket": "",
            #         "storage_folder": "files",
            #         "storage_region": "",
            #     },
            # )

            # Use ROOT Data Collection if data_collection_id is not provided
            if not data_collection_id:
                collection = self.data_collection_repository.get_root_data_collection()
                data_collection_id = collection.id
            else:
                collection = self.data_collection_repository.get_data_collection_by_id(
                    data_collection_id
                )

            data_store = collection.collection_config.get("data_store")

            if not data_store:
                raise HTTPException(
                    status_code=422,
                    detail=f"Data Store is missing for Collection {collection.name}. Please check and retry.",
                )

            # One tree: schema/collection_name (main files + .processed/)
            _schema = (self.organization_schema or "public").strip() or "public"
            _col = collection.name.lower().replace(" ", "_")
            data_store["storage_folder"] = f"{_schema}/{_col}"

            # Define the local folder path for storing data files and create the directory if it doesn't exist
            folder_path = os.path.join("data")
            os.makedirs(folder_path, exist_ok=True)

            for data_file in data_files:
                file_type = data_file.filename.split(".")[-1].lower()
                if file_type not in self.allowed_extensions:
                    logger.warning(f"File type not supported: {data_file.filename}")
                    upload_failures.append(
                        {
                            "name": data_file.filename,
                            "error": "File type not supported.",
                        }
                    )
                    continue

                if data_file.size > self.max_file_size:
                    logger.warning(
                        f"File size larger than {self.max_file_size/1048576} MB not supported: {data_file.filename}"
                    )
                    upload_failures.append(
                        {
                            "name": data_file.filename,
                            "error": f"File size larger than {self.max_file_size/1048576} MB not supported.",
                        }
                    )
                    continue

                # Check if a data file with the same name already exists in the folder and skip execution for it
                if self.data_file_repository.get_data_file_by_name_and_folder(
                    data_file.filename, data_collection_id
                ):
                    logger.warning(
                        f"File with same name already exists in the Collection: {data_file.filename}"
                    )
                    upload_failures.append(
                        {
                            "name": data_file.filename,
                            "error": "File with same name already exists in the Collection.",
                        }
                    )
                    continue

                # Write the data file to the local directory
                data_file_path = os.path.join(folder_path, data_file.filename)
                with open(data_file_path, "wb") as file:
                    file.write(data_file.file.read())

                # Upload the data file to the data store and get the remote_url
                remote_url = self.upload_file_to_minio(
                    data_store=data_store,
                    file_path=data_file_path,
                    upload_path=f"{data_store['storage_folder']}/{data_file.filename}",
                )

                # if data_store["storage_type"] == "remote":
                #     remote_url = S3Bucket(
                #         self.organization_schema, data_store
                #     ).upload_file(
                #         data_file_path,
                #         f"{data_store['storage_folder']}/{data_file.filename}",
                #     )
                # else:
                #     remote_url = FileSystem(
                #         self.organization_schema, data_store
                #     ).upload_file(
                #         data_file_path,
                #         f"{data_store['storage_folder']}/{data_file.filename}",
                #     )

                # Save the data file information in the database
                saved_data_file = self.data_file_repository.create_data_file(
                    {
                        "name": data_file.filename,
                        "size": data_file.size,
                        "mime_type": data_file.content_type,
                        "source_type": source,
                        "source_metadata": {"file_path": remote_url},
                        "status": [
                            {
                                "status": "QUEUED",
                                "timestamp": str(datetime.now()),
                            }
                        ],
                        "collection_id": data_collection_id,
                    }
                )

                if saved_data_file:
                    knowledge_extraction = collection.collection_config.get(
                        "advanced_knowledge_extraction"
                    )
                    document_record = {
                        "data_file_uuid": saved_data_file.id,
                        "data_file_name": saved_data_file.name,
                        "data_file_size": saved_data_file.size,
                        "source_metadata": saved_data_file.source_metadata,
                        "data_file_path": saved_data_file.source_metadata.get(
                            "file_path"
                        ),
                        "data_file_source": saved_data_file.source_type,
                        "collection_name": collection.name,
                        "collection_index": collection.index_name,
                        "collection_id": saved_data_file.collection_id,
                        "knowledge_extraction": knowledge_extraction,
                    }
                    celery.send_task(
                        "index_document",
                        args=[self.organization_schema, document_record],
                        queue="knowledge_queue",
                    )

                    # Convert the saved data file to a dictionary and append to the uploaded data files list
                    data_file = DataFileDetail.model_validate(saved_data_file)
                    upload_successes.append(data_file.model_dump())

                else:
                    logger.error(
                        f"Failed to save data file in the database: {data_file.filename}"
                    )
                    upload_failures.append(
                        {
                            "name": data_file.filename,
                            "error": "An error occurred while uploading the file.",
                        }
                    )

                # Remove the local data file after processing
                os.remove(data_file_path)

            return {
                "upload_successes": upload_successes,
                "upload_failures": upload_failures,
            }

        except HTTPException as http_error:
            # Catch FastAPI HTTPExceptions
            logger.error(f"HTTPException occurred: {http_error.detail}")
            raise http_error
        except Exception as e:
            logger.error(f"Error while uploading data files: {e}")
            return None
        
    def upload_file_to_minio(
        self, data_store: Dict, file_path: str, upload_path: str
    ) -> Optional[str]:
        """
        Uploads a file to MinIO storage (knowledge collection storage).

        Args:
            data_store (Dict): Storage configuration (bucket from env if not set).
            file_path (str): Local path to the file that needs to be uploaded.
            upload_path (str): Destination path where the file should be uploaded.

        Returns:
            str: Object path (key) of the uploaded file if successful, otherwise None.
        """
        try:
            return MinIOStorage(data_store=data_store).upload_file(
                source_path=file_path, destination_path=upload_path
            )

        except Exception as e:
            logger.error(f"An error occurred in upload_file to MinIO: {e}")
            return None
    
    def download_file_from_minio(self, file_path) -> Optional[bytes]:
        """
        Download a file from MinIO storage.

        file_path: MinIO object key (e.g. schema/collection_name/file.pdf).
        Returns:
            bytes: File content if successful, None if failed.
        """
        try:
            content = MinIOStorage().get_object(file_path)
            if content is not None:
                return content
            logger.error("Failed to download the file from MinIO")
        except Exception as e:
            logger.exception(f"An error occurred in download_file from MinIO: {e}")
            return None  
      
    def upload_file(
        self, data_store: Dict, file_path: str, upload_path: str
    ) -> Optional[str]:
        """
        Uploads a file to a remote or local storage based on the specified data store.

        Args:
            data_store (Dict): Storage configuration to upload the file.
            file_path (str): Local path to the file that needs to be uploaded.
            upload_path (str): Destination path where the file should be uploaded.

        Returns:
            str: URL or path of the uploaded file if successful, otherwise None.
        """
        try:
            if data_store.get("storage_type") == "remote":
                remote_url = AWSS3(
                    organization_schema=self.organization_schema, data_store=data_store
                ).upload_file(source_path=file_path, destination_path=upload_path)
            else:
                remote_url = FileSystem(data_store=data_store).upload_file(
                    source_path=file_path, destination_path=upload_path
                )

            return remote_url

        except Exception as e:
            logger.error(f"An error occurred in upload_file: {e}")
            return None

    def download_file(self, **kwargs) -> Optional[bytes]:
        """
        Download a file from S3 or local filesystem.
        (SharePoint not in use; re-enable in code and doc when needed.)

        S3 example:
            download_file(
                file_path="https://my-bucket.amazonaws.com/documents/report.pdf"
            )

        Local filesystem example:
            download_file(
                file_path="/home/user/documents/report.pdf"
            )

        Returns:
            bytes: File content if successful, None if failed.
        """
        try:
            file_source_type = kwargs.get("file_source_type")
            source_metadata = kwargs.get("source_metadata", {})
            file_path = kwargs.get("file_path") or source_metadata.get("file_path")
            if not file_path:
                logger.error("File path is required")
                return None

            # SharePoint not in use; re-enable when needed.
            # if file_source_type == "SharePoint":
            #     site_id = source_metadata.get("site_id")
            #     file_id = source_metadata.get("file_id")
            #     if site_id and file_id:
            #         sharepoint = Sharepoint(self.db)
            #         response = sharepoint.download_file_content(site_id, file_id)
            #         if response.status_code == 200:
            #             return response.content
            #         logger.error("Failed to download the file from SharePoint")
            #     else:
            #         logger.error("Missing SharePoint file metadata")
            #     return None

            if (
                file_path and file_path.startswith("https") and "amazonaws" in file_path
            ):
                aws_s3 = AWSS3(self.organization_schema)
                presigned_url = aws_s3.generate_presigned_url(file_path)
                response = requests.get(presigned_url)
                if response.status_code == 200:
                    return response.content
                logger.error("Failed to download the file from S3")
                return None

            elif file_path and os.path.exists(file_path):
                with open(file_path, "rb") as file:
                    return file.read()

            else:
                logger.error("File does not exist at the specified path")
                return None

        except Exception as e:
            logger.exception(f"An error occurred in download_file: {e}")
            return None

    def upload_processed_file(
        self,
        data_store: Dict,
        content: str,
        collection_name: str,
        original_filename: str,
        file_suffix: str,
    ) -> Optional[str]:
        """
        Upload processed file (chunks or extracted content) to MinIO storage.

        Args:
            data_store (Dict): Storage configuration
            content (str): File content to upload
            collection_name (str): Name of the collection
            original_filename (str): Original document filename
            file_suffix (str): Suffix for processed file (e.g., "_chunks.json" or "_extracted_content.txt")

        Returns:
            str: Remote file path if successful, None otherwise
        """
        try:
            # Generate filename without extension
            base_name = os.path.splitext(original_filename)[0]
            processed_filename = f"{base_name}{file_suffix}"

            # Same path convention as raw files: schema/collection_name/.processed/...
            _schema = (self.organization_schema or "public").strip() or "public"
            _col = collection_name.lower().replace(" ", "_")
            storage_folder = f"{_schema}/{_col}"
            storage_path = f"{storage_folder}/.processed/{processed_filename}"

            # Write content to temp file
            temp_file = f"/tmp/{processed_filename}"
            with open(temp_file, "w", encoding="utf-8") as f:
                f.write(content)

            # Upload to MinIO only (knowledge collection storage)
            remote_url = self.upload_file_to_minio(
                data_store=data_store, file_path=temp_file, upload_path=storage_path
            )

            # Clean up temp file
            os.remove(temp_file)

            logger.info(
                f"Successfully uploaded processed file: {processed_filename} to {remote_url}"
            )
            return remote_url

        except Exception as e:
            logger.error(f"Error uploading processed file: {e}")
            return None

    def download_processed_file(
        self, data_store: Dict, file_path: str
    ) -> Optional[str]:
        """
        Download and read processed file from MinIO storage.

        Args:
            data_store (Dict): Storage configuration (unused; MinIO only).
            file_path (str): MinIO object key for the processed file.

        Returns:
            str: File content as string if successful, None otherwise
        """
        try:
            # Processed files are stored in MinIO only (knowledge collection storage)
            content = self.download_file_from_minio(file_path)

            if content:
                return content.decode("utf-8")

            logger.warning(f"Failed to download processed file: {file_path}")
            return None

        except Exception as e:
            logger.error(f"Error downloading processed file: {e}")
            return None
