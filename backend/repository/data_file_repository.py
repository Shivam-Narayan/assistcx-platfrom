# Custom libraries
from logger import configure_logging
from integrations.minio_storage.client import MinIOStorage
from schemas.data_file_schema import DataFileStatus
from utils.environment import environment
from utils.schema_utils import get_current_schema

# Database modules
from models.data_file import DataFile

# Default libraries
from typing import Any, Optional, Tuple, Dict, List
from uuid import UUID

# Installed libraries
from fastapi import HTTPException
from sqlalchemy import String, asc, cast, desc, or_, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.sql import func


logger = configure_logging(__name__)


class DataFileRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_data_file(self, data_file_data: dict) -> Optional[DataFile]:
        new_data_file = DataFile(**data_file_data)
        try:
            self.db.add(new_data_file)
            self.db.commit()
            self.db.refresh(new_data_file)
            return new_data_file
        except IntegrityError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy IntegrityError: {e}")
            raise HTTPException(
                status_code=409,
                detail="Data File with same name already exists in this folder. Please check and retry.",
            )
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def update_data_file(self, update_data: dict) -> Optional[DataFile]:
        try:
            data_file_uuid = update_data.get("data_file_uuid")
            query_filter = DataFile.id == data_file_uuid
            data_file = self.db.query(DataFile).filter(query_filter).first()
            if not data_file:
                return None
            for key, value in update_data.items():
                if hasattr(data_file, key):
                    setattr(data_file, key, value)
            self.db.commit()
            return data_file
        except IntegrityError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy IntegrityError: {e}")
            raise HTTPException(
                status_code=409,
                detail="Data File with same name already exists in this folder. Please check and retry.",
            )
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def update_file_metadata(
        self,
        data_file_id: UUID,
        metadata_updates: Optional[dict] = None,
        fields_to_remove: Optional[List[str]] = None,
    ) -> Optional[DataFile]:
        """
        Update specific fields in the file_metadata JSONB column without overriding the entire metadata.

        Args:
            data_file_id (UUID): The ID of the data file to update
            metadata_updates (dict): Dictionary containing the metadata fields to update
            fields_to_remove (List[str]): List of metadata fields to remove

        Returns:
            Optional[DataFile]: Updated data file object or None if error
        """
        try:
            data_file = (
                self.db.query(DataFile).filter(DataFile.id == data_file_id).first()
            )
            if not data_file:
                logger.warning(f"Data file with ID {data_file_id} not found")
                return None

            # Get existing metadata and merge with new metadata
            current_metadata = data_file.file_metadata or {}
            updated_metadata = {**current_metadata, **(metadata_updates or {})}

            # Remove specified fields if provided
            if fields_to_remove:
                for field in fields_to_remove:
                    updated_metadata.pop(field, None)

            # Update with new metadata fields
            data_file.file_metadata = updated_metadata

            # Mark the JSONB column as modified for SQLAlchemy to track changes
            flag_modified(data_file, "file_metadata")

            self.db.commit()
            self.db.refresh(data_file)
            logger.info(
                f"Successfully updated file metadata for data file {data_file_id}"
            )
            return data_file

        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error updating file metadata: {e}")
            return None

    def append_data_file_status(
        self, data_file_id: UUID, status: Dict
    ) -> Optional[DataFile]:
        data_file = self.db.query(DataFile).filter(DataFile.id == data_file_id).first()
        if not data_file:
            return None

        try:
            # Convert current status to Pydantic model and append new status
            current_progress = [
                DataFileStatus(**status) for status in data_file.status or []
            ]
            current_progress.append(DataFileStatus(**status))

            # Update the data file status
            data_file.status = [progress.model_dump() for progress in current_progress]

            self.db.commit()
            self.db.refresh(data_file)
            return data_file
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            self.db.rollback()
            return None

    def get_collection_stats(self, collection_id: UUID) -> Dict[str, any]:
        """
        Get statistics for a collection including file count and total size
        """
        try:
            query = self.db.query(
                func.count(DataFile.id).label("file_count"),
                func.coalesce(func.sum(DataFile.size), 0).label("total_size"),
            ).filter(DataFile.collection_id == collection_id)

            result = query.first()
            return {
                "file_count": result.file_count if result else 0,
                "total_size": result.total_size if result else 0,
            }
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error in get_collection_stats: {e}")
            return {"file_count": 0, "total_size": 0}

    def get_collection_documents(self, collection_id: UUID) -> List[Dict[str, Any]]:
        """
        Get all document IDs alongwith their status for a collection efficiently.

        Args:
            collection_id: UUID of the data collection

        Returns:
            List: List of dictionaries with document IDs and their status
        """
        try:
            result = (
                self.db.query(DataFile.id, DataFile.status)
                .filter(DataFile.collection_id == collection_id)
                .all()
            )
            documents = [{"id": row.id, "status": row.status} for row in result]
            return documents
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error in get_collection_documents: {e}")
            return []

    def get_data_file_by_id(self, identifier: UUID) -> Optional[DataFile]:
        try:
            return self.db.query(DataFile).filter(DataFile.id == identifier).first()
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def get_data_file_by_name_and_folder(
        self, name: str, collection_id: UUID
    ) -> Optional[DataFile]:
        try:
            return (
                self.db.query(DataFile)
                .filter(DataFile.name == name, DataFile.collection_id == collection_id)
                .first()
            )
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def get_all_data_files(
        self,
        collection_id: Optional[UUID] = None,
        page: int = 1,
        page_size: int = 10,
        filters: Optional[Dict[str, any]] = None,
        sort_by: str = "updated_at",
        sort_order: str = "desc",
    ) -> Tuple[List[DataFile], int]:

        # Ensure page and page_size are positive integers
        page = max(1, int(page if page else 1))
        page_size = max(1, int(page_size if page_size else 10))
        skip = (page - 1) * page_size
        query = self.db.query(DataFile)

        # Fetch data files for specific folder or ROOT folder
        if collection_id:
            query = query.filter(DataFile.collection_id == collection_id)
        # else:
        #     data_folder_repository = CollectionRepository(self.db)
        #     root_data_folder = data_folder_repository.get_root_data_folder()
        #     query = query.filter(DataFile.collection_id == root_data_folder.id)

        # Apply filters
        if filters:
            for key, values in filters.items():
                if hasattr(DataFile, key):
                    # Special handling for status filter
                    if key == "status":
                        if isinstance(values, str):
                            values = [values]
                        query = query.filter(
                            text("status -> -1 ->> 'status' = ANY(:statuses)")
                        ).params(statuses=values)
                    else:
                        if isinstance(values, list):
                            # Handle multiple values for the same filter key
                            condition = or_(
                                *(getattr(DataFile, key) == value for value in values)
                            )
                            query = query.filter(condition)
                        else:
                            query = query.filter(getattr(DataFile, key) == values)

        # Apply sorting
        if hasattr(DataFile, sort_by):
            order = (
                asc(getattr(DataFile, sort_by))
                if sort_order == "asc"
                else desc(getattr(DataFile, sort_by))
            )
            query = query.order_by(order)

        try:
            data_files = query.offset(skip).limit(page_size).all()
            total = query.count()
            return data_files, total
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return [], 0

    def search_data_files(
        self,
        keyword: str = None,
        collection_id: Optional[UUID] = None,  # Added this parameter
        page: int = 1,
        page_size: int = 10,
        filters: Optional[Dict[str, any]] = None,
        sort_by: str = "updated_at",
        sort_order: str = "desc",
    ) -> Tuple[List[DataFile], int]:

        # Ensure page and page_size are positive integers
        page = max(1, int(page if page else 1))
        page_size = max(1, int(page_size if page_size else 10))
        skip = (page - 1) * page_size
        query = self.db.query(DataFile)

        # Apply collection_id filter if provided
        if collection_id:
            query = query.filter(DataFile.collection_id == collection_id)
        # else:
        #     data_folder_repository = CollectionRepository(self.db)
        #     root_data_folder = data_folder_repository.get_root_data_folder()
        #     query = query.filter(DataFile.collection_id == root_data_folder.id)

        # Apply filters
        if filters:
            for key, values in filters.items():
                if hasattr(DataFile, key):
                    # Special handling for status filter
                    if key == "status":
                        if isinstance(values, str):
                            values = [values]
                        query = query.filter(
                            text("status -> -1 ->> 'status' = ANY(:statuses)")
                        ).params(statuses=values)
                    else:
                        if isinstance(values, list):
                            # Handle multiple values for the same filter key
                            condition = or_(
                                *(getattr(DataFile, key) == value for value in values)
                            )
                            query = query.filter(condition)
                        else:
                            query = query.filter(getattr(DataFile, key) == values)

        # Apply search
        if keyword:
            query = query.filter(
                or_(
                    DataFile.name.ilike(f"%{keyword}%"),
                    cast(DataFile.file_metadata, String).ilike(f"%{keyword}%"),
                )
            )

        # Apply sorting
        if hasattr(DataFile, sort_by):
            order = (
                asc(getattr(DataFile, sort_by))
                if sort_order == "asc"
                else desc(getattr(DataFile, sort_by))
            )
            query = query.order_by(order)

        try:
            data_files = query.offset(skip).limit(page_size).all()
            total = query.count()
            return data_files, total
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return [], 0

    def delete_data_file(self, identifier: UUID) -> Optional[bool]:
        try:
            organization_schema = get_current_schema(self.db) if self.db else "public"

            data_file = (
                self.db.query(DataFile).filter(DataFile.id == identifier).first()
            )
            if not data_file:
                return False

            if data_file.source_type == "SharePoint":
                self.db.delete(data_file)
                self.db.commit()
                return True

            file_path = data_file.source_metadata.get("file_path")

            if file_path:
                from repository.data_collection_repository import (
                    DataCollectionRepository,
                )

                data_collection_repository = DataCollectionRepository(self.db)
                data_collection = data_collection_repository.get_data_collection_by_id(
                    data_file.collection_id
                )

                data_store = (
                    data_collection.collection_config.get("data_store")
                    if data_collection and data_collection.collection_config
                    else None
                )

                if not data_store:
                    logger.warning(f"Missing data store for data file: {data_file.id}")
                    return False

                if not MinIOStorage(data_store).delete_file(
                    data_file.source_metadata.get("file_path")
                ):
                    logger.warning(f"Failed to delete data file: {data_file.id}")
                    return False

                # Delete processed files (chunks and extracted content)
                if data_file.file_metadata:
                    chunks_path = data_file.file_metadata.get("chunks_file_path")
                    content_path = data_file.file_metadata.get(
                        "extracted_content_file_path"
                    )

                    if chunks_path:
                        try:
                            MinIOStorage(data_store).delete_file(chunks_path)
                            logger.info(f"Deleted chunks file: {chunks_path}")
                        except Exception as e:
                            logger.warning(f"Failed to delete chunks file: {e}")

                    if content_path:
                        try:
                            MinIOStorage(data_store).delete_file(content_path)
                            logger.info(
                                f"Deleted extracted content file: {content_path}"
                            )
                        except Exception as e:
                            logger.warning(
                                f"Failed to delete extracted content file: {e}"
                            )

            self.db.delete(data_file)
            self.db.commit()
            return True

        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            self.db.rollback()
            return False

    def delete_data_files_by_folder(self, collection_id: UUID) -> bool:
        """
        Deletes all data files within a specific data collection.
        """
        try:
            organization_schema = get_current_schema(self.db) if self.db else "public"

            from repository.data_collection_repository import DataCollectionRepository

            data_collection_repository = DataCollectionRepository(self.db)
            data_collection = data_collection_repository.get_data_collection_by_id(
                collection_id
            )

            data_store = (
                data_collection.collection_config.get("data_store")
                if data_collection and data_collection.collection_config
                else None
            )

            data_files = (
                self.db.query(DataFile)
                .filter(DataFile.collection_id == collection_id)
                .all()
            )

            if not data_files:
                logger.warning(f"No files to delete from collection: {collection_id}")
                return True

            deleted_count = 0

            for data_file in data_files:
                file_path = data_file.source_metadata.get("file_path")

                if data_file.source_type == "SharePoint" or not file_path:
                    self.db.delete(data_file)
                    deleted_count += 1
                else:
                    if MinIOStorage(data_store).delete_file(
                        data_file.source_metadata.get("file_path")
                    ):
                        if data_file.file_metadata:
                            chunks_path = data_file.file_metadata.get(
                                "chunks_file_path"
                            )
                            content_path = data_file.file_metadata.get(
                                "extracted_content_file_path"
                            )
                            if chunks_path:
                                try:
                                    MinIOStorage(data_store).delete_file(chunks_path)
                                except Exception as e:
                                    logger.warning(
                                        f"Failed to delete chunks file: {e}"
                                    )
                            if content_path:
                                try:
                                    MinIOStorage(data_store).delete_file(content_path)
                                except Exception as e:
                                    logger.warning(
                                        f"Failed to delete content file: {e}"
                                    )

                        self.db.delete(data_file)
                        deleted_count += 1
                    else:
                        logger.warning(
                            f"Failed to delete file: {data_file.id} from collection: {collection_id}"
                        )

            self.db.commit()
            logger.info(
                f"Deleted {deleted_count} of {len(data_files)} files from collection: {collection_id}"
            )
            return deleted_count == len(data_files)

        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error in delete_data_files_by_folder: {e}")
            self.db.rollback()
            return False
