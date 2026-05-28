# Custom libraries
from logger import configure_logging
from utils.schema_utils import get_current_schema

# Database modules
from models.user_access import UserAccess
from models.user_role import UserRole
from models.user import User

# Default libraries
from uuid import UUID
from typing import Optional, Tuple, Dict, List

# Installed libraries
from fastapi import HTTPException
from sqlalchemy import asc, desc, or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session


logger = configure_logging(__name__)


class UserRoleRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_user_role(self, user_role_data: Dict) -> Optional[UserRole]:
        try:
            user_role = UserRole(**user_role_data)

            organization_schema = get_current_schema(self.db)
            if organization_schema != "public" and user_role.name == "ROOT":
                raise HTTPException(
                    status_code=400,
                    detail="Creating user role with name ROOT not allowed.",
                )

            self.db.add(user_role)
            self.db.commit()
            self.db.refresh(user_role)
            return user_role
        except IntegrityError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy IntegrityError: {e}")
            raise HTTPException(
                status_code=409,
                detail="User role already exists.",
            )
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            self.db.rollback()
            return None

    def update_user_role(self, update_data: dict) -> Optional[UserRole]:
        try:
            name_to_update = update_data.get("name")

            user_role = (
                self.db.query(UserRole).filter(UserRole.name == name_to_update).first()
            )

            if user_role:
                # Update the fields based on the provided data
                for field, value in update_data.items():
                    setattr(user_role, field, value)
            else:
                # Create a new user role if the name is missing
                user_role = UserRole(**update_data)
                self.db.add(user_role)

            self.db.commit()
            self.db.refresh(user_role)
            return user_role

        except IntegrityError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy IntegrityError: {e}")
            raise HTTPException(
                status_code=409,
                detail="User role update failed due to integrity constraint.",
            )
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def update_user_role_by_id(self, update_data: dict) -> Optional[UserRole]:
        try:
            user_role_uuid = update_data.get("user_role_uuid")
            user_role = (
                self.db.query(UserRole).filter(UserRole.id == user_role_uuid).first()
            )

            if not user_role:
                return None

            for key, value in update_data.items():
                if hasattr(user_role, key):
                    setattr(user_role, key, value)

            self.db.commit()
            return user_role

        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def get_role_by_id(self, identifier: UUID) -> Optional[UserRole]:
        try:
            return self.db.query(UserRole).filter(UserRole.id == identifier).first()
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def get_all_user_roles(
        self,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
        filters: Optional[Dict[str, any]] = None,
        sort_by: str = "updated_at",
        sort_order: str = "desc",
    ) -> Tuple[List[UserRole], int]:
        query = self.db.query(UserRole)

        # Filter out user roles with name ROOT
        query = query.filter(UserRole.name != "ROOT")

        # Apply filters
        if filters:
            for key, values in filters.items():
                if hasattr(UserRole, key):
                    if isinstance(values, list):
                        # Handle multiple values for the same filter key
                        condition = or_(
                            *(getattr(UserRole, key) == value for value in values)
                        )
                        query = query.filter(condition)
                    else:
                        query = query.filter(getattr(UserRole, key) == values)

        # Apply sorting
        if hasattr(UserRole, sort_by):
            order = (
                asc(getattr(UserRole, sort_by))
                if sort_order == "asc"
                else desc(getattr(UserRole, sort_by))
            )
            query = query.order_by(order)

        try:
            total = query.count()

            # Only apply pagination if both page and page_size are provided
            if page and page_size:
                skip = (page - 1) * page_size
                user_roles = query.offset(skip).limit(page_size).all()
            else:
                user_roles = query.all()

            return user_roles, total
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return [], 0

    def search_user_roles(
        self,
        keyword: str,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
        filters: Optional[Dict[str, any]] = None,
        sort_by: str = "updated_at",
        sort_order: str = "desc",
    ) -> Tuple[List[UserRole], int]:
        query = self.db.query(UserRole)

        # Filter out user roles with name ROOT
        query = query.filter(UserRole.name != "ROOT")

        # Apply filters
        if filters:
            for key, values in filters.items():
                if hasattr(UserRole, key):
                    if isinstance(values, list):
                        # Handle multiple values for the same filter key
                        condition = or_(
                            *(getattr(UserRole, key) == value for value in values)
                        )
                        query = query.filter(condition)
                    else:
                        query = query.filter(getattr(UserRole, key) == values)

        # Apply search
        if keyword:
            query = query.filter(
                or_(
                    UserRole.name.ilike(f"%{keyword}%"),
                    UserRole.description.ilike(f"%{keyword}%"),
                )
            )

        # Apply sorting
        if hasattr(UserRole, sort_by):
            order = (
                asc(getattr(UserRole, sort_by))
                if sort_order == "asc"
                else desc(getattr(UserRole, sort_by))
            )
            query = query.order_by(order)

        try:
            total = query.count()

            # Only apply pagination if both page and page_size are provided
            if page and page_size:
                skip = (page - 1) * page_size
                user_roles = query.offset(skip).limit(page_size).all()
            else:
                user_roles = query.all()

            return user_roles, total
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return [], 0

    def delete_user_role_by_id(self, identifier: UUID) -> Optional[bool]:
        """
        Deletes an existing user role based on its identifier.
        """
        user_role = self.db.query(UserRole).filter(UserRole.id == identifier).first()
        if not user_role:
            return False
        if user_role.default_role:
            raise HTTPException(
                status_code=403,
                detail=f"Default roles cannot be deleted.",
            )
        users = (
            self.db.query(User)
            .join(UserAccess, User.id == UserAccess.user_id)
            .filter(UserAccess.role_id == user_role.id)
            .all()
        )
        if users:
            raise HTTPException(
                status_code=409,
                detail=f"The {user_role.name} is in use. Please delete the associated users first.",
            )
        try:
            self.db.delete(user_role)
            self.db.commit()
            return True
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            self.db.rollback()
            return False

    def remove_permissions_roles(self, permission_key: str):
        try:
            # Fetch all user roles
            user_roles, _ = self.get_all_user_roles()

            # Iterate through user roles
            for user_role in user_roles:
                # Filter out permissions that don't match the permission_key
                user_role.role_permissions = [
                    permission
                    for permission in user_role.role_permissions
                    if permission != permission_key
                ]

            # Commit changes
            self.db.commit()
            logger.info(f"Removed permission '{permission_key}' from all user roles")

        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Error removing permissions from user roles: {e}")

    # def get_paginated_user_roles(
    #     self,
    #     page: int = 1,
    #     page_size: int = 10,
    #     filters: Optional[Dict[str, any]] = None,
    #     sort_by: str = "created_at",
    #     sort_order: str = "desc",
    # ) -> Tuple[List[UserRole], int]:
    #     skip = (page - 1) * page_size
    #     query = self.db.query(UserRole)

    #     # Apply filters
    #     if filters:
    #         for key, values in filters.items():
    #             if hasattr(UserRole, key):
    #                 if isinstance(values, list):
    #                     # Handle multiple values for the same filter key
    #                     condition = or_(
    #                         *(getattr(UserRole, key) == value for value in values)
    #                     )
    #                     query = query.filter(condition)
    #                 else:
    #                     query = query.filter(getattr(UserRole, key) == values)

    #     # Apply sorting
    #     if hasattr(UserRole, sort_by):
    #         order = (
    #             asc(getattr(UserRole, sort_by))
    #             if sort_order == "asc"
    #             else desc(getattr(UserRole, sort_by))
    #         )
    #         query = query.order_by(order)

    #     try:
    #         user_roles = query.offset(skip).limit(page_size).all()
    #         total = query.count()
    #         return user_roles, total
    #     except SQLAlchemyError as e:
    #         logger.error(f"SQLAlchemy Error: {e}")
    #         return [], 0
        
    # def paginated_search_user_roles(
    #     self,
    #     keyword: str,
    #     page: int = 1,
    #     page_size: int = 10,
    #     filters: Optional[Dict[str, any]] = None,
    #     sort_by: str = "created_at",
    #     sort_order: str = "desc",
    # ) -> Tuple[List[UserRole], int]:
    #     skip = (page - 1) * page_size
    #     query = self.db.query(UserRole)

    #     # Apply filters
    #     if filters:
    #         for key, values in filters.items():
    #             if hasattr(UserRole, key):
    #                 if isinstance(values, list):
    #                     # Handle multiple values for the same filter key
    #                     condition = or_(
    #                         *(getattr(UserRole, key) == value for value in values)
    #                     )
    #                     query = query.filter(condition)
    #                 else:
    #                     query = query.filter(getattr(UserRole, key) == values)

    #     # Apply search
    #     if keyword:
    #         query = query.filter(
    #             or_(
    #                 UserRole.name.ilike(f"%{keyword}%"),
    #                 UserRole.description.ilike(f"%{keyword}%"),
    #             )
    #         )

    #     # Apply sorting
    #     if hasattr(UserRole, sort_by):
    #         order = (
    #             asc(getattr(UserRole, sort_by))
    #             if sort_order == "asc"
    #             else desc(getattr(UserRole, sort_by))
    #         )
    #         query = query.order_by(order)

    #     try:
    #         user_roles = query.offset(skip).limit(page_size).all()
    #         total = query.count()
    #         return user_roles, total
    #     except SQLAlchemyError as e:
    #         logger.error(f"SQLAlchemy Error: {e}")
    #         return [], 0

    # def remove_permissions_roles(self, permission_key: str):
    #     try:
    #         # Fetch all user roles
    #         user_roles, _ = self.get_all_user_roles()

    #         # Iterate through user roles
    #         for user_role in user_roles:
    #             # Filter out permissions that don't match the permission_key
    #             user_role.role_permissions = [
    #                 permission
    #                 for permission in user_role.role_permissions
    #                 if permission["feature"] != permission_key
    #             ]

    #         # Commit changes
    #         self.db.commit()
    #         logger.info(f"Removed permission '{permission_key}' from all user roles")

    #     except SQLAlchemyError as e:
    #         self.db.rollback()
    #         logger.error(f"Error removing permissions from user roles: {e}")
