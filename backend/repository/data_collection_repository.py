# Custom libraries
from logger import configure_logging

# Database modules
from models.data_collection import DataCollection
from repository.data_file_repository import DataFileRepository
from repository.user_access_repository import UserAccessRepository

# Default libraries
from typing import Optional, Tuple, Union, Dict, List
from uuid import UUID

# Installed libraries
from fastapi import HTTPException
from sqlalchemy import asc, desc, or_
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.orm import Session

logger = configure_logging(__name__)


class DataCollectionRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_data_collection(
        self, data_folder_data: dict
    ) -> Optional[DataCollection]:
        if not data_folder_data.get("parent_id") and not data_folder_data["is_root"]:
            root_data_folder = self.get_root_data_collection()
            data_folder_data["parent_id"] = root_data_folder.id
        existing_data_folder = (
            self.db.query(DataCollection)
            .filter(
                DataCollection.name == data_folder_data["name"],
                DataCollection.parent_id == data_folder_data.get("parent_id"),
            )
            .first()
        )
        if existing_data_folder:
            raise HTTPException(
                status_code=409,
                detail="Data Folder already exists. Please check and retry.",
            )
        new_data_folder = DataCollection(**data_folder_data)
        try:
            self.db.add(new_data_folder)
            self.db.commit()
            self.db.refresh(new_data_folder)
            return new_data_folder
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def update_data_collection(self, update_data: dict) -> Optional[DataCollection]:
        data_collection_uuid = update_data.get("data_collection_uuid")
        query_filter = DataCollection.id == data_collection_uuid
        data_collection = self.db.query(DataCollection).filter(query_filter).first()
        if not data_collection:
            return None
        try:
            # Check for existing data folder with the same name under the same parent
            if "name" in update_data:
                existing_data_collection = (
                    self.db.query(DataCollection)
                    .filter(
                        DataCollection.name == update_data["name"],
                        DataCollection.parent_id == data_collection.parent_id,
                        DataCollection.id != data_collection_uuid,
                    )
                    .first()
                )
                if existing_data_collection:
                    raise HTTPException(
                        status_code=409,
                        detail="Data Folder already exists. Please check and retry.",
                    )

            for key, value in update_data.items():
                if hasattr(data_collection, key):
                    # Special handling for collection_config: merge instead of replace
                    # This preserves immutable fields like embedding_model
                    if key == "collection_config" and value is not None:
                        existing_config = data_collection.collection_config or {}
                        # Merge new values into existing config
                        merged_config = {**existing_config, **value}
                        setattr(data_collection, key, merged_config)
                    else:
                        setattr(data_collection, key, value)
            self.db.commit()
            self.db.refresh(data_collection)
            return data_collection
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            self.db.rollback()
            return None

    def get_data_collection_by_id(self, identifier: UUID) -> Optional[DataCollection]:
        try:
            data_folder = (
                self.db.query(DataCollection)
                .filter(DataCollection.id == identifier)
                .first()
            )
            if data_folder:
                data_file_repository = DataFileRepository(self.db)
                stats = data_file_repository.get_collection_stats(data_folder.id)
                data_folder.file_count = stats["file_count"]
                data_folder.total_size = stats["total_size"]
            return data_folder
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def get_data_collection_by_index_name(
        self, index_name: str
    ) -> Optional[DataCollection]:
        """Get a data collection by its Milvus index name."""
        try:
            data_folder = (
                self.db.query(DataCollection)
                .filter(DataCollection.index_name == index_name)
                .first()
            )
            return data_folder
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def get_embedding_model(self, index_name: str) -> str:
        """Get the embedding model configured for a collection by its Milvus index name."""
        collection = self.get_data_collection_by_index_name(index_name)
        if collection and collection.collection_config:
            return collection.collection_config.get("embedding_model") or ""
        return ""

    def get_collections_by_user(
        self,
        user_id: UUID,
    ) -> List[DataCollection]:
        try:
            user_access_repository = UserAccessRepository(self.db)
            user_access = user_access_repository.get_user_access_by_user_id(
                user_uuid=user_id
            )

            # If no user access or data_access is null, return all collections
            if not user_access or not user_access.data_access:
                data_folders = self.get_all_user_collections()
                return data_folders

            # Get view_collections from data_access
            view_collections = user_access.data_access.get("view_collections", {})
            name_filter = view_collections.get("name", True)

            query = self.db.query(DataCollection)

            # If name_filter is True, return all collections
            if name_filter is True:
                data_folders = self.get_all_user_collections()
                return data_folders
            # If name_filter is a list, filter collections by those names
            elif isinstance(name_filter, list):
                query = query.filter(DataCollection.name.in_(name_filter))

            data_folders = query.all()

            # Add stats to each folder
            data_file_repository = DataFileRepository(self.db)
            for folder in data_folders:
                stats = data_file_repository.get_collection_stats(folder.id)
                folder.file_count = stats["file_count"]
                folder.total_size = stats["total_size"]

            return data_folders

        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return []

    def get_private_data_collection_by_owner_id(
        self, user_id: str
    ) -> Optional[DataCollection]:
        try:
            return (
                self.db.query(DataCollection)
                .filter(
                    DataCollection.owner_id == user_id,
                    DataCollection.availability == "PRIVATE",
                )
                .first()
            )
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def get_all_user_collections(self) -> List[DataCollection]:
        try:
            query = self.db.query(DataCollection)
            root_data_folder = self.get_root_data_collection()
            query = query.filter(DataCollection.parent_id == root_data_folder.id)

            data_folders = query.all()

            # Add stats to each folder
            data_file_repository = DataFileRepository(self.db)
            for folder in data_folders:
                stats = data_file_repository.get_collection_stats(folder.id)
                folder.file_count = stats["file_count"]
                folder.total_size = stats["total_size"]

            return data_folders
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return []

    def get_root_data_collection(self) -> Optional[DataCollection]:
        try:
            root_data_folder = (
                self.db.query(DataCollection)
                .filter(DataCollection.name == "ROOT", DataCollection.is_root == True)
                .first()
            )
            if not root_data_folder:
                root_data_folder = self.create_data_collection(
                    {
                        "name": "ROOT",
                        "index_name": "root",
                        "description": "System ROOT data folder.",
                        "status": "ACTIVE",
                        "is_root": True,
                        "parent_id": None,
                    }
                )
            if root_data_folder:
                data_file_repository = DataFileRepository(self.db)
                stats = data_file_repository.get_collection_stats(root_data_folder.id)
                root_data_folder.file_count = stats["file_count"]
                root_data_folder.total_size = stats["total_size"]
            return root_data_folder
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def get_data_collection_by_name_and_parent_id(
        self, name: str, folder_id: UUID
    ) -> Optional[DataCollection]:
        try:
            data_folder = (
                self.db.query(DataCollection)
                .filter(
                    DataCollection.name == name, DataCollection.parent_id == folder_id
                )
                .first()
            )
            if data_folder:
                data_file_repository = DataFileRepository(self.db)
                stats = data_file_repository.get_collection_stats(data_folder.id)
                data_folder.file_count = stats["file_count"]
                data_folder.total_size = stats["total_size"]
            return data_folder
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def get_all_data_collections(
        self,
        collection_id: Optional[UUID] = None,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
        filters: Optional[Dict[str, any]] = None,
        sort_by: str = "updated_at",
        sort_order: str = "desc",
    ) -> Tuple[List[DataCollection], int]:
        query = self.db.query(DataCollection)

        # Exclude PRIVATE data collections
        query = query.filter(DataCollection.availability != "PRIVATE")

        # Fetch data folders for specific folder or ROOT folder
        if collection_id:
            query = query.filter(DataCollection.parent_id == collection_id)
        else:
            root_data_folder = self.get_root_data_collection()
            query = query.filter(DataCollection.parent_id == root_data_folder.id)

        # Apply filters
        if filters:
            for key, values in filters.items():
                if hasattr(DataCollection, key):
                    if isinstance(values, list):
                        # Handle multiple values for the same filter key
                        condition = or_(
                            *(getattr(DataCollection, key) == value for value in values)
                        )
                        query = query.filter(condition)
                    else:
                        query = query.filter(getattr(DataCollection, key) == values)

        # Apply sorting
        if hasattr(DataCollection, sort_by):
            order = (
                asc(getattr(DataCollection, sort_by))
                if sort_order == "asc"
                else desc(getattr(DataCollection, sort_by))
            )
            query = query.order_by(order)

        try:
            total = query.count()

            # Only apply pagination if both page and page_size are provided
            if page and page_size:
                skip = (page - 1) * page_size
                data_folders = query.offset(skip).limit(page_size).all()
            else:
                data_folders = query.all()

            # Create DataFileRepository instance
            data_file_repository = DataFileRepository(self.db)

            # Add stats to each folder
            for folder in data_folders:
                stats = data_file_repository.get_collection_stats(folder.id)
                folder.file_count = stats["file_count"]
                folder.total_size = stats["total_size"]

            return data_folders, total
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return [], 0

    def search_data_collections(
        self,
        keyword: str,
        collection_id: Optional[UUID] = None,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
        filters: Optional[Dict[str, any]] = None,
        sort_by: str = "updated_at",
        sort_order: str = "desc",
    ) -> Tuple[List[DataCollection], int]:
        query = self.db.query(DataCollection)

        # Exclude PRIVATE data collections
        query = query.filter(DataCollection.availability != "PRIVATE")

        # Apply folder_id filter if provided
        if collection_id:
            query = query.filter(DataCollection.parent_id == collection_id)
        else:
            root_data_folder = self.get_root_data_collection()
            query = query.filter(DataCollection.parent_id == root_data_folder.id)

        # Apply filters
        if filters:
            for key, values in filters.items():
                if hasattr(DataCollection, key):
                    if isinstance(values, list):
                        condition = or_(
                            *(getattr(DataCollection, key) == value for value in values)
                        )
                        query = query.filter(condition)
                    else:
                        query = query.filter(getattr(DataCollection, key) == values)

        # Apply search
        if keyword:
            query = query.filter(
                or_(
                    DataCollection.name.ilike(f"%{keyword}%"),
                    DataCollection.description.ilike(f"%{keyword}%"),
                )
            )

        # Apply sorting
        if hasattr(DataCollection, sort_by):
            order = (
                asc(getattr(DataCollection, sort_by))
                if sort_order == "asc"
                else desc(getattr(DataCollection, sort_by))
            )
            query = query.order_by(order)

        try:
            total = query.count()

            # Only apply pagination if both page and page_size are provided
            if page and page_size:
                skip = (page - 1) * page_size
                data_folders = query.offset(skip).limit(page_size).all()
            else:
                data_folders = query.all()

            # Create DataFileRepository instance
            data_file_repository = DataFileRepository(self.db)

            # Add stats to each folder
            for folder in data_folders:
                stats = data_file_repository.get_collection_stats(folder.id)
                folder.file_count = stats["file_count"]
                folder.total_size = stats["total_size"]

            return data_folders, total
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return [], 0

    def delete_data_collection(self, identifier: UUID) -> bool:
        data_folder = (
            self.db.query(DataCollection)
            .filter(DataCollection.id == identifier)
            .first()
        )
        if not data_folder:
            return False
        data_files, total = DataFileRepository(self.db).get_all_data_files(
            collection_id=data_folder.id
        )
        if data_files:
            raise HTTPException(
                status_code=409,
                detail="Knowledge Collection cannot be deleted without deleting all data files inside it. Please check and retry.",
            )
        try:
            self.db.delete(data_folder)
            self.db.commit()
            return True
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            self.db.rollback()
            return False
