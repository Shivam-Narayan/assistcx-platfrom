# Custom libraries
from integrations.office_365.outlook import Outlook
from logger import configure_logging
from utils.authentication import Authentication
from utils.schema_utils import get_user_schema

# Database modules
from models.user_group import UserGroup
from models.user_access import UserAccess
from models.user import User
from repository.user_access_repository import UserAccessRepository
from repository.user_group_repository import UserGroupRepository
from repository.user_role_repository import UserRoleRepository
from schemas.user_schema import UserDetail

# Default libraries
from datetime import datetime
import os
from typing import Any, Optional, Tuple, Union, Dict, List
from uuid import UUID

# Installed libraries
from fastapi import HTTPException
from sqlalchemy import asc, desc, or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, joinedload
import asyncio


logger = configure_logging(logger_name=__name__)

authentication = Authentication()


class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_user(self, user_data: dict) -> Optional[User]:
        hashed_data = authentication.hash_password(user_data["password"])

        user_schema = get_user_schema(user_data["email"])
        if user_schema:
            logger.error(f"User already exists {user_data['email']}")
            raise HTTPException(
                status_code=409,
                detail="User already exists. Please check and retry.",
            )

        if user_data.get("role_id") is not None:
            user_role_repository = UserRoleRepository(self.db)
            user_role = user_role_repository.get_role_by_id(user_data.get("role_id"))
            if not user_role:
                logger.error(f"User Role does not exist: {user_data.get('role_id')}")
                raise HTTPException(
                    status_code=400,
                    detail="The specified User Role does not exist. Please check and retry.",
                )

        outlook = Outlook(self.db)
        office_365_profile = outlook.get_user_profile(user_data["email"])
        user_config = office_365_profile or {}

        new_user = User(
            email=user_data["email"],
            hashed_password=hashed_data["hashed_password"],
            salt=hashed_data["salt"],
            user_id=user_data.get("user_id"),
            first_name=user_data.get("first_name"),
            last_name=user_data.get("last_name"),
            user_config=user_config,
            updated_at=datetime.now(),
            # Add other fields as needed
        )

        try:
            self.db.add(new_user)
            self.db.commit()
            self.db.refresh(new_user)

            if (
                user_data.get("role_id")
                or user_data.get("data_access")
                # or user_data.get("app_access")
                or user_data.get("user_group_ids")
            ):
                new_user_access = UserAccess(
                    user_id=new_user.id,
                    role_id=user_data.get("role_id"),
                    data_access=user_data.get("data_access"),
                    # app_access=user_data.get("app_access"),
                    user_group_ids=user_data.get("user_group_ids"),
                )
                try:
                    self.db.add(new_user_access)
                    self.db.commit()
                    self.db.refresh(new_user_access)
                except SQLAlchemyError as e:
                    logger.error(f"SQLAlchemy Error: {e}")
                    self.db.rollback()

            user_details = {
                "id": new_user.id,
                "email": new_user.email,
                "first_name": new_user.first_name,
                "last_name": new_user.last_name,
                "user_id": new_user.user_id,
                "account_status": new_user.account_status,
                "user_config": new_user.user_config,
                "last_login": new_user.last_login,
                "created_at": new_user.created_at,
                "updated_at": new_user.updated_at,
            }

            if new_user_access:
                user_details["role_id"] = new_user_access.role_id
                user_details["data_access"] = new_user_access.data_access
                # user_details["app_access"] = new_user_access.app_access
                user_details["role_key"] = user_role.role_key if user_role else None
                user_details["user_group_ids"] = new_user_access.user_group_ids
                if new_user_access.user_group_ids:
                    user_group_keys = []
                    user_group_repository = UserGroupRepository(self.db)
                    for user_group_id in new_user_access.user_group_ids:
                        user_group = asyncio.run(
                            user_group_repository.get_user_group_by_id(
                                UUID(user_group_id)
                            )
                        )
                        if user_group:
                            user_group_keys.append(user_group.key)
                    user_details["user_group_keys"] = user_group_keys
                else:
                    user_details["user_group_keys"] = None

            return UserDetail(**user_details)

        except IntegrityError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy IntegrityError: {e}")
            raise HTTPException(
                status_code=409,
                detail="User already exists.",
            )
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            self.db.rollback()
            return None

    def update_user(self, update_data: dict) -> Optional[User]:
        identifier = update_data.get("user_uuid") or update_data.get("email")
        # Determine the type of identifier and construct the query filter
        if isinstance(identifier, UUID):
            query_filter = User.id == identifier
        elif isinstance(identifier, str):
            query_filter = User.email == identifier
        else:
            logger.error(
                f"Identifier must be a UUID or email string, received: {identifier}"
            )
            raise ValueError(
                f"Identifier must be a UUID or email string, received: {identifier}"
            )

        user = self.db.query(User).filter(query_filter).first()
        if not user:
            return None

        if "email" in update_data and user.email != update_data["email"]:
            user_schema = get_user_schema(update_data["email"])
            if user_schema:
                logger.error(f"User already exists {update_data['email']}")
                raise HTTPException(
                    status_code=404,
                    detail="User already exists. Please check and retry.",
                )

        # "updated_at" should change only for user feature updates. And not for every log in.
        if "last_login" not in update_data:
            update_data["updated_at"] = datetime.now()

        role_id = update_data.get("role_id")
        data_access = update_data.get("data_access")
        # app_access = update_data.get("app_access")
        user_group_ids = update_data.get("user_group_ids")

        outlook = Outlook(self.db)
        office_365_profile = outlook.get_user_profile(
            update_data.get("email") or user.email
        )
        update_data["user_config"] = office_365_profile or {}

        try:
            for key, value in update_data.items():
                if key == "password":
                    hashed_data = authentication.hash_password(value)
                    user.hashed_password = hashed_data["hashed_password"]
                    user.salt = hashed_data["salt"]
                elif hasattr(user, key):
                    setattr(user, key, value)

            # Update or create UserAccess
            user_access = (
                self.db.query(UserAccess).filter(UserAccess.user_id == user.id).first()
            )
            if role_id:
                user_role_repository = UserRoleRepository(self.db)
                user_role = user_role_repository.get_role_by_id(role_id)
                if not user_role:
                    logger.error(f"User Role does not exist: {role_id}")
                    raise HTTPException(
                        status_code=400,
                        detail="The specified User Role does not exist. Please check and retry.",
                    )
            else:
                user_role = None

            if user_access:
                if role_id is not None:
                    user_access.role_id = role_id
                if data_access is not None:
                    user_access.data_access = data_access
                # if app_access is not None:
                #     user_access.app_access = app_access
                if user_group_ids is not None:
                    user_access.user_group_ids = user_group_ids
            elif any([role_id, data_access, user_group_ids]):
                user_access = UserAccess(
                    user_id=user.id,
                    role_id=role_id,
                    data_access=data_access,
                    # app_access=app_access,
                    user_group_ids=user_group_ids,
                )
                self.db.add(user_access)
            self.db.commit()
            self.db.refresh(user)

            user_details = {
                "id": user.id,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "user_id": user.user_id,
                "account_status": user.account_status,
                "user_config": user.user_config,
                "last_login": user.last_login,
                "created_at": user.created_at,
                "updated_at": user.updated_at,
            }

            if user_access:
                user_details["role_id"] = user_access.role_id
                user_details["data_access"] = user_access.data_access
                # user_details["app_access"] = user_access.app_access
                user_details["role_key"] = user_role.role_key if user_role else None
                user_details["user_group_ids"] = user_access.user_group_ids
                if user_access.user_group_ids:
                    user_group_keys = []
                    user_group_repository = UserGroupRepository(self.db)
                    for user_group_id in user_access.user_group_ids:
                        user_group = asyncio.run(
                            user_group_repository.get_user_group_by_id(
                                UUID(user_group_id)
                            )
                        )
                        if user_group:
                            user_group_keys.append(user_group.key)
                    user_details["user_group_keys"] = user_group_keys
                else:
                    user_details["user_group_keys"] = None

            return UserDetail(**user_details)

        except IntegrityError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy IntegrityError: {e}")
            raise HTTPException(
                status_code=409,
                detail="User already exists.",
            )
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def create_or_update_user(self, data: dict) -> Optional[User]:
        identifier = data.get("user_uuid") or data.get("email")
        if not identifier:
            logger.error("Either UUID or email is required for user operations")
            raise ValueError("Either UUID or email is required for user operations")

        # Determine the type of identifier and construct the appropriate query filter
        if isinstance(identifier, UUID):
            query_filter = User.id == identifier
        else:  # Assuming identifier is email as string
            query_filter = User.email == identifier

        try:
            existing_user = self.db.query(User).filter(query_filter).first()
            if existing_user:
                return self.update_user(data)
            else:
                return self.create_user(data)
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def get_user_by_id(
        self, identifier: Union[UUID, str], user_details: Optional[bool] = False
    ) -> Optional[User]:
        # Build query filter
        if isinstance(identifier, UUID):
            query_filter = User.id == identifier
        elif isinstance(identifier, str):
            query_filter = (
                User.email == identifier
                if "@" in identifier
                else User.user_id == identifier
            )
        else:
            raise ValueError("Identifier must be a UUID or user_id/email string")

        try:
            # Eager load accesses and groups only if user_details is requested
            query = self.db.query(User).filter(query_filter)
            if user_details:
                query = query.options(joinedload(User.user_access))

            user = query.first()
            if not user:
                return None

            if user_details:
                # Get user access record
                user_access_repository = UserAccessRepository(self.db)
                user_access = user_access_repository.get_user_access_by_user_id(user.id)

                if user_access:
                    user.role_id = user_access.role_id
                    user.data_access = user_access.data_access
                    # user.app_access = user_access.app_access
                    user.user_group_ids = user_access.user_group_ids

                    # Fetch user role information
                    user_role_repository = UserRoleRepository(self.db)
                    user_role = user_role_repository.get_role_by_id(user_access.role_id)
                    user.role_key = user_role.role_key if user_role else None

                    # Fetch user group information
                    if user_access.user_group_ids:
                        user_group_keys = []
                        user_group_repository = UserGroupRepository(self.db)
                        for user_group_id in user_access.user_group_ids:
                            user_group = asyncio.run(
                                user_group_repository.get_user_group_by_id(
                                    UUID(user_group_id)
                                )
                            )
                            if user_group:
                                user_group_keys.append(user_group.key)
                        user.user_group_keys = user_group_keys
                    else:
                        user.user_group_keys = None

            return user

        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def get_user_summaries_by_ids(
        self, user_ids: List[UUID]
    ) -> Dict[UUID, Dict[str, Any]]:
        """
        One query: load users for the given UUIDs and return a map
        ``uuid`` -> ``{"user_id", "name", "email_id"}`` for API payloads.
        """
        if not user_ids:
            return {}
        try:
            users = self.db.query(User).filter(User.id.in_(user_ids)).all()
            user_summary_map: Dict[UUID, Dict[str, Any]] = {}
            for user_record in users:
                first_name = (user_record.first_name or "").strip()
                last_name = (user_record.last_name or "").strip()
                display_name = (
                    f"{first_name} {last_name}".strip() or (user_record.email or "")
                )
                user_summary_map[user_record.id] = {
                    "user_id": str(user_record.id),
                    "name": display_name,
                    "email_id": user_record.email,
                }
            return user_summary_map
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return {}

    def get_all_users(
        self,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
        filters: Optional[Dict[str, any]] = None,
        sort_by: str = "updated_at",
        sort_order: str = "desc",
    ) -> Tuple[List[User], int]:
        query = self.db.query(User)

        # Filter out users with email equals to PLATFORM_ROOT_USER
        query = query.filter(User.email != os.getenv("PLATFORM_ROOT_USER"))

        # Apply filters
        if filters:
            for key, values in filters.items():
                if hasattr(User, key):
                    if isinstance(values, list):
                        # Handle multiple values for the same filter key
                        condition = or_(
                            *(getattr(User, key) == value for value in values)
                        )
                        query = query.filter(condition)
                    else:
                        query = query.filter(getattr(User, key) == values)

        # Apply sorting
        if hasattr(User, sort_by):
            order = (
                asc(getattr(User, sort_by))
                if sort_order == "asc"
                else desc(getattr(User, sort_by))
            )
            query = query.order_by(order)

        try:
            total = query.count()

            # Only apply pagination if both page and page_size are provided
            if page and page_size:
                skip = (page - 1) * page_size
                users = query.offset(skip).limit(page_size).all()
            else:
                users = query.all()

            for user in users:
                user_access_repository = UserAccessRepository(self.db)
                user_access = user_access_repository.get_user_access_by_user_id(user.id)
                if user_access:
                    user.role_id = user_access.role_id
                    user.data_access = user_access.data_access
                    # user.app_access = user_access.app_access
                    user.user_group_ids = user_access.user_group_ids
                    user_role_repository = UserRoleRepository(self.db)
                    user_role = user_role_repository.get_role_by_id(user_access.role_id)
                    user.role_key = user_role.role_key if user_role else None
                    if user_access.user_group_ids:
                        user_group_keys = []
                        user_group_repository = UserGroupRepository(self.db)
                        for user_group_id in user_access.user_group_ids:
                            user_group = asyncio.run(
                                user_group_repository.get_user_group_by_id(
                                    UUID(user_group_id)
                                )
                            )
                            if user_group:
                                user_group_keys.append(user_group.key)
                        user.user_group_keys = user_group_keys
                    else:
                        user.user_group_keys = None

            return users, total
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return [], 0

    def search_users(
        self,
        keyword: str,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
        filters: Optional[Dict[str, any]] = None,
        sort_by: str = "updated_at",
        sort_order: str = "desc",
    ) -> Tuple[List[User], int]:
        query = self.db.query(User)

        # Filter out users with email equals to PLATFORM_ROOT_USER
        query = query.filter(User.email != os.getenv("PLATFORM_ROOT_USER"))

        # Apply filters
        if filters:
            for key, values in filters.items():
                if hasattr(User, key):
                    if isinstance(values, list):
                        # Handle multiple values for the same filter key
                        condition = or_(
                            *(getattr(User, key) == value for value in values)
                        )
                        query = query.filter(condition)
                    else:
                        query = query.filter(getattr(User, key) == values)

        # Apply search
        if keyword:
            query = query.filter(
                or_(
                    User.email.ilike(f"%{keyword}%"),
                    User.first_name.ilike(f"%{keyword}%"),
                    User.last_name.ilike(f"%{keyword}%"),
                    User.user_id.ilike(f"%{keyword}%"),
                    User.account_status.ilike(f"%{keyword}%"),
                )
            )

        # Apply sorting
        if hasattr(User, sort_by):
            order = (
                asc(getattr(User, sort_by))
                if sort_order == "asc"
                else desc(getattr(User, sort_by))
            )
            query = query.order_by(order)

        try:
            total = query.count()

            # Only apply pagination if both page and page_size are provided
            if page and page_size:
                skip = (page - 1) * page_size
                users = query.offset(skip).limit(page_size).all()
            else:
                users = query.all()

            for user in users:
                user_access_repository = UserAccessRepository(self.db)
                user_access = user_access_repository.get_user_access_by_user_id(user.id)
                if user_access:
                    user.role_id = user_access.role_id
                    user.data_access = user_access.data_access
                    # user.app_access = user_access.app_access
                    user.user_group_ids = user_access.user_group_ids
                    user_role_repository = UserRoleRepository(self.db)
                    user_role = user_role_repository.get_role_by_id(user_access.role_id)
                    user.role_key = user_role.role_key if user_role else None
                    if user_access.user_group_ids:
                        user_group_keys = []
                        user_group_repository = UserGroupRepository(self.db)
                        for user_group_id in user_access.user_group_ids:
                            user_group = asyncio.run(
                                user_group_repository.get_user_group_by_id(
                                    UUID(user_group_id)
                                )
                            )
                            if user_group:
                                user_group_keys.append(user_group.key)
                        user.user_group_keys = user_group_keys
                    else:
                        user.user_group_keys = None

            return users, total
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return [], 0

    def delete_user_by_id(self, identifier: UUID) -> Optional[bool]:
        """
        Deletes an existing user based on its identifier.
        """
        user = self.db.query(User).filter(User.id == identifier).first()
        if not user:
            return False
        try:
            self.db.delete(user)
            self.db.commit()
            return True
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            self.db.rollback()
            return False

    # def paginated_get_all_users(
    #     self,
    #     page: int = 1,
    #     page_size: int = 10,
    #     filters: Optional[Dict[str, any]] = None,
    #     sort_by: str = "created_at",
    #     sort_order: str = "desc",
    # ) -> Tuple[List[User], int]:
    #     skip = (page - 1) * page_size
    #     query = self.db.query(User)

    #     # Filter out users with email equals to PLATFORM_ROOT_USER
    #     query = query.filter(User.email != os.getenv("PLATFORM_ROOT_USER"))

    #     # Apply filters
    #     if filters:
    #         for key, values in filters.items():
    #             if hasattr(User, key):
    #                 if isinstance(values, list):
    #                     # Handle multiple values for the same filter key
    #                     condition = or_(
    #                         *(getattr(User, key) == value for value in values)
    #                     )
    #                     query = query.filter(condition)
    #                 else:
    #                     query = query.filter(getattr(User, key) == values)

    #     # Apply sorting
    #     if hasattr(User, sort_by):
    #         order = (
    #             asc(getattr(User, sort_by))
    #             if sort_order == "asc"
    #             else desc(getattr(User, sort_by))
    #         )
    #         query = query.order_by(order)

    #     try:
    #         users = query.offset(skip).limit(page_size).all()
    #         total = query.count()

    #         user_schemas = []
    #         for user in users:
    #             # Fetch data access information after updates
    #             user_access_repository = UserAccessRepository(self.db)
    #             data_access = user_access_repository.get_user_access_by_user_id(user.id)

    #             # Construct return data
    #             user_details = {
    #                 "id": user.id,
    #                 "email": user.email,
    #                 "first_name": user.first_name,
    #                 "last_name": user.last_name,
    #                 "user_id": user.user_id,
    #                 "account_status": user.account_status,
    #                 "last_login": user.last_login,
    #                 "created_at": user.created_at,
    #                 "updated_at": user.updated_at,
    #             }

    #             if data_access:
    #                 user_details["role_id"] = data_access.role_id
    #                 user_details["data_access"] = data_access.data_access

    #                 # Fetch user role information
    #                 user_role_repository = UserRoleRepository(self.db)
    #                 user_role = user_role_repository.get_role_by_id(data_access.role_id)
    #                 if user_role:
    #                     user_details["role_key"] = user_role.role_key
    #                 else:
    #                     logger.warning("User role not found for the given role_id")
    #                     user_details["role_key"] = None

    #             user_schema = UserDetail(**user_details)
    #             user_schemas.append(user_schema)

    #         return user_schemas, total
    #     except SQLAlchemyError as e:
    #         logger.error(f"SQLAlchemy Error: {e}")
    #         return [], 0

    # def paginated_search_user(
    #     self,
    #     keyword: str,
    #     page: int = 1,
    #     page_size: int = 10,
    #     filters: Optional[Dict[str, any]] = None,
    #     sort_by: str = "created_at",
    #     sort_order: str = "desc",
    # ) -> Tuple[List[User], int]:
    #     skip = (page - 1) * page_size
    #     query = self.db.query(User)

    #     # Filter out users with email equals to PLATFORM_ROOT_USER
    #     query = query.filter(User.email != os.getenv("PLATFORM_ROOT_USER"))

    #     # Apply filters
    #     if filters:
    #         for key, values in filters.items():
    #             if hasattr(User, key):
    #                 if isinstance(values, list):
    #                     # Handle multiple values for the same filter key
    #                     condition = or_(
    #                         *(getattr(User, key) == value for value in values)
    #                     )
    #                     query = query.filter(condition)
    #                 else:
    #                     query = query.filter(getattr(User, key) == values)

    #     # Apply search
    #     if keyword:
    #         query = query.filter(
    #             or_(
    #                 User.email.ilike(f"%{keyword}%"),
    #                 User.first_name.ilike(f"%{keyword}%"),
    #                 User.last_name.ilike(f"%{keyword}%"),
    #                 User.user_id.ilike(f"%{keyword}%"),
    #                 User.account_status.ilike(f"%{keyword}%"),
    #             )
    #         )

    #     # Apply sorting
    #     if hasattr(User, sort_by):
    #         order = (
    #             asc(getattr(User, sort_by))
    #             if sort_order == "asc"
    #             else desc(getattr(User, sort_by))
    #         )
    #         query = query.order_by(order)

    #     try:
    #         users = query.offset(skip).limit(page_size).all()
    #         total = query.count()

    #         user_schemas = []
    #         for user in users:
    #             # Fetch data access information after updates
    #             user_access_repository = UserAccessRepository(self.db)
    #             data_access = user_access_repository.get_user_access_by_user_id(user.id)

    #             # Construct return data
    #             user_details = {
    #                 "id": user.id,
    #                 "email": user.email,
    #                 "first_name": user.first_name,
    #                 "last_name": user.last_name,
    #                 "user_id": user.user_id,
    #                 "account_status": user.account_status,
    #                 "last_login": user.last_login,
    #                 "created_at": user.created_at,
    #                 "updated_at": user.updated_at,
    #             }

    #             if data_access:
    #                 user_details["role_id"] = data_access.role_id
    #                 user_details["data_access"] = data_access.data_access

    #                 # Fetch user role information
    #                 user_role_repository = UserRoleRepository(self.db)
    #                 user_role = user_role_repository.get_role_by_id(data_access.role_id)
    #                 if user_role:
    #                     user_details["role_key"] = user_role.role_key
    #                 else:
    #                     logger.warning("User role not found for the given role_id")
    #                     user_details["role_key"] = None

    #             user_schema = UserDetail(**user_details)
    #             user_schemas.append(user_schema)

    #         return user_schemas, total
    #     except SQLAlchemyError as e:
    #         logger.error(f"SQLAlchemy Error: {e}")
    #         return [], 0
