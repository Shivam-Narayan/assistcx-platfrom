# Custom libraries
from logger import configure_logging

# Database modules
from models.user_group import UserGroup
from models.user_access import UserAccess

# Default libraries
from typing import Any, Dict, List, Optional, Tuple, Union
from uuid import UUID

# Installed libraries
from fastapi import HTTPException
from sqlalchemy import asc, desc, or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session


logger = configure_logging(__name__)


class UserGroupRepository:
    def __init__(self, db: Session):
        self.db = db

    async def create_user_group(self, user_group_data: Dict) -> Optional[UserGroup]:
        """
        Creates a new user group.
        """
        try:
            user_group = UserGroup(**user_group_data)
            self.db.add(user_group)
            self.db.commit()
            self.db.refresh(user_group)
            return user_group

        except IntegrityError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy IntegrityError: {e}")
            raise HTTPException(
                status_code=409,
                detail="User Group already exists. Please check and retry.",
            )
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    async def update_user_group_by_id(self, update_data: dict) -> Optional[UserGroup]:
        """
        Updates an existing user group based on its UUID.
        """
        try:
            user_group_uuid = update_data.get("user_group_uuid")
            user_group = (
                self.db.query(UserGroup).filter(UserGroup.id == user_group_uuid).first()
            )

            if not user_group:
                return None

            for key, value in update_data.items():
                if hasattr(user_group, key) and key != "user_group_uuid":
                    setattr(user_group, key, value)

            self.db.commit()
            self.db.refresh(user_group)
            return user_group

        except IntegrityError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy IntegrityError: {e}")
            raise HTTPException(
                status_code=409,
                detail="User Group already exists. Please check and retry.",
            )
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    async def get_user_group_by_id(
        self, identifier: Union[UUID, str]
    ) -> Optional[UserGroup]:
        """
        Retrieves a user group by its UUID or key.
        """
        if isinstance(identifier, UUID):
            query_filter = UserGroup.id == identifier
        elif isinstance(identifier, str):
            query_filter = UserGroup.key == identifier
        else:
            raise ValueError("Identifier must be a UUID or a User Group key.")

        try:
            return self.db.query(UserGroup).filter(query_filter).first()

        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    async def get_user_groups_by_ids(self, group_ids: List[str]) -> List[UserGroup]:
        """
        Batch fetch multiple user groups by their IDs.

        OPTIMIZED: Single query with IN clause instead of N separate queries.

        Args:
            group_ids: List of user group ID strings

        Returns:
            List of UserGroup objects
        """
        if not group_ids:
            return []

        try:
            # Convert string IDs to UUIDs
            uuid_ids = [UUID(gid) for gid in group_ids]

            # Single query with IN clause
            user_groups = (
                self.db.query(UserGroup)
                .filter(UserGroup.id.in_(uuid_ids))
                .all()
            )

            return user_groups

        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error fetching user groups by IDs: {e}")
            return []
        except ValueError as e:
            logger.error(f"Invalid UUID in group_ids: {e}")
            return []

    async def get_user_groups(
        self,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
        filters: Optional[Dict[str, Any]] = None,
        sort_by: str = "updated_at",
        sort_order: str = "desc",
    ) -> Tuple[List[UserGroup], int]:
        """
        Retrieves all user groups with filtering, sorting, and pagination.
        """
        query = self.db.query(UserGroup)

        # Apply filters
        if filters:
            for key, values in filters.items():
                if hasattr(UserGroup, key):
                    if isinstance(values, list):
                        # Handle multiple values for the same filter key
                        condition = or_(
                            *(getattr(UserGroup, key) == value for value in values)
                        )
                        query = query.filter(condition)
                    else:
                        query = query.filter(getattr(UserGroup, key) == values)

        # Apply sorting
        if hasattr(UserGroup, sort_by):
            order = (
                asc(getattr(UserGroup, sort_by))
                if sort_order == "asc"
                else desc(getattr(UserGroup, sort_by))
            )
            query = query.order_by(order)

        try:
            total = query.count()

            # Only apply pagination if both page and page_size are provided
            if page and page_size and page > 0:
                skip = (page - 1) * page_size
                user_groups = query.offset(skip).limit(page_size).all()
            else:
                user_groups = query.all()

            return user_groups, total

        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return [], 0

    async def search_user_groups(
        self,
        keyword: str,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
        filters: Optional[Dict[str, Any]] = None,
        sort_by: str = "updated_at",
        sort_order: str = "desc",
    ) -> Tuple[List[UserGroup], int]:
        """
        Searches user groups by keyword with filtering, sorting, and pagination.
        """
        query = self.db.query(UserGroup)

        # Apply filters
        if filters:
            for key, values in filters.items():
                if hasattr(UserGroup, key):
                    if isinstance(values, list):
                        # Handle multiple values for the same filter key
                        condition = or_(
                            *(getattr(UserGroup, key) == value for value in values)
                        )
                        query = query.filter(condition)
                    else:
                        query = query.filter(getattr(UserGroup, key) == values)

        # Apply search
        if keyword:
            query = query.filter(
                or_(
                    UserGroup.name.ilike(f"%{keyword}%"),
                    UserGroup.key.ilike(f"%{keyword}%"),
                    UserGroup.description.ilike(f"%{keyword}%"),
                )
            )

        # Apply sorting
        if hasattr(UserGroup, sort_by):
            order = (
                asc(getattr(UserGroup, sort_by))
                if sort_order == "asc"
                else desc(getattr(UserGroup, sort_by))
            )
            query = query.order_by(order)

        try:
            total = query.count()

            # Only apply pagination if both page and page_size are provided
            if page and page_size and page > 0:
                skip = (page - 1) * page_size
                user_groups = query.offset(skip).limit(page_size).all()
            else:
                user_groups = query.all()

            return user_groups, total

        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return [], 0

    async def delete_user_group_by_id(self, identifier: UUID) -> bool:
        """
        Deletes an existing user group based on its UUID.
        """
        user_group = self.db.query(UserGroup).filter(UserGroup.id == identifier).first()
        if not user_group:
            return False

        try:
            # Find all user access containing the user group and remove the user group from their user_group_ids
            user_access = (
                self.db.query(UserAccess)
                .filter(UserAccess.user_group_ids.contains([str(identifier)]))
                .all()
            )
            for access in user_access:
                if access.user_group_ids and str(identifier) in access.user_group_ids:
                    access.user_group_ids = [
                        user_group_id
                        for user_group_id in access.user_group_ids
                        if user_group_id != str(identifier)
                    ]

            self.db.delete(user_group)
            self.db.commit()
            return True

        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            self.db.rollback()
            return False
