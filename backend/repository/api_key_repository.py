# Custom libraries
from logger import configure_logging

# Database modules
from models.api_key import ApiKey
from repository.user_repository import UserRepository
from sqlalchemy.orm import Session

# Default libraries
from typing import Optional, List, Dict, Union
from uuid import UUID

# Installed libraries
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import desc, asc, or_


logger = configure_logging(__name__)


class ApiKeyRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_api_key(self, api_key_data: Dict) -> Optional[ApiKey]:
        """
        Creates a new API key from API key data.
        """
        new_api_key = ApiKey(**api_key_data)
        try:
            self.db.add(new_api_key)
            self.db.commit()
            self.db.refresh(new_api_key)
            return new_api_key
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def update_api_key(self, update_data: dict) -> Optional[ApiKey]:
        identifier = update_data.get("api_key_uuid")
        query_filter = (
            ApiKey.id == identifier
            if isinstance(identifier, UUID)
            else ApiKey.key_hash == identifier
        )

        api_key = self.db.query(ApiKey).filter(query_filter).first()
        if not api_key:
            return None

        try:
            for key, value in update_data.items():
                if hasattr(api_key, key):
                    setattr(api_key, key, value)
            self.db.commit()
            self.db.refresh(api_key)
            return api_key

        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def get_api_key_by_id(self, identifier: Union[UUID, str]) -> Optional[ApiKey]:
        """
        Retrieves an API key based on its identifier.
        """
        try:
            if isinstance(identifier, UUID):
                query_filter = ApiKey.id == identifier
            elif isinstance(identifier, str):
                query_filter = ApiKey.key_hash == identifier

            return self.db.query(ApiKey).filter(query_filter).first()

        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def get_api_keys(
        self,
        filters: Optional[Dict[str, any]] = None,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
        sort_by: Optional[str] = "created_at",
        sort_order: Optional[str] = "desc",
    ) -> List[ApiKey]:
        """
        Retrieves API keys with optional filters and sorting.
        """
        try:
            query = self.db.query(ApiKey)

            # Apply filters
            if filters:
                for key, value in filters.items():
                    if hasattr(ApiKey, key):
                        if isinstance(value, list):
                            query = query.filter(getattr(ApiKey, key).in_(value))
                        else:
                            query = query.filter(getattr(ApiKey, key) == value)

            # Apply sorting
            if hasattr(ApiKey, sort_by):
                order = (
                    asc(getattr(ApiKey, sort_by))
                    if sort_order == "asc"
                    else desc(getattr(ApiKey, sort_by))
                )
                query = query.order_by(order)

            if page and page_size:
                skip = (page - 1) * page_size
                api_keys = query.offset(skip).limit(page_size).all()
            else:
                api_keys = query.all()

            for api_key in api_keys:
                if api_key.user_id:
                    user = UserRepository(self.db).get_user_by_id(UUID(api_key.user_id))
                    if user:
                        names = filter(None, [user.first_name, user.last_name])
                        api_key.user_name = " ".join(names)

            return api_keys

        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return []

    def search_api_keys(
        self,
        keyword: str,
        filters: Optional[Dict[str, any]] = None,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
        sort_by: Optional[str] = "created_at",
        sort_order: Optional[str] = "desc",
    ) -> List[ApiKey]:
        """
        Searches API keys by keyword with optional filters and sorting.
        """
        try:
            query = self.db.query(ApiKey)

            # Apply filters
            if filters:
                for key, value in filters.items():
                    if hasattr(ApiKey, key):
                        if isinstance(value, list):
                            query = query.filter(getattr(ApiKey, key).in_(value))
                        else:
                            query = query.filter(getattr(ApiKey, key) == value)

            # Apply keyword search
            if keyword:
                query = query.filter(
                    or_(
                        ApiKey.name.ilike(f"%{keyword}%"),
                    )
                )

            # Apply sorting
            if hasattr(ApiKey, sort_by):
                order = (
                    asc(getattr(ApiKey, sort_by))
                    if sort_order == "asc"
                    else desc(getattr(ApiKey, sort_by))
                )
                query = query.order_by(order)

            if page and page_size:
                skip = (page - 1) * page_size
                api_keys = query.offset(skip).limit(page_size).all()
            else:
                api_keys = query.all()

            for api_key in api_keys:
                if api_key.user_id:
                    user = UserRepository(self.db).get_user_by_id(UUID(api_key.user_id))
                    if user:
                        names = filter(None, [user.first_name, user.last_name])
                        api_key.user_name = " ".join(names)

            return api_keys

        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return []

    def delete_api_key_by_id(self, identifier: UUID) -> bool:
        """
        Deletes an API key based on its identifier.
        """
        try:
            api_key = self.db.query(ApiKey).filter(ApiKey.id == identifier).first()
            if not api_key:
                return False

            self.db.delete(api_key)
            self.db.commit()
            return True

        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error: {e}")
            return False
